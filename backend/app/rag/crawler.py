"""SSRF-safe breadth-first web crawler for `link` knowledge-base sources.

This module is deliberately **pure**: it takes a URL and a config, and returns
data. It never touches Postgres or Chroma — persisting pages and embedding their
text is `app.rag.jobs`' job. That separation is what makes the interesting
parts (address filtering, depth/page limits, robots.txt, dedupe) testable without
a database, a vector store, or an API key.

Every outbound request goes through `app.rag.net.safe_fetch`, which rejects
private/loopback/link-local/metadata addresses before connecting *and* re-checks
after each redirect hop. Every fetched page goes through
`app.rag.sanitize.parse_html`, which removes scripts/styles/iframes with
their contents before any text is kept.

Two documented deviations from the obvious design:

* **`crawl()` returns a `CrawlResult`, not a bare list.** It carries the page list
  plus per-URL skip/error diagnostics, which the job handler records in
  `embedding_jobs.stats` so a half-successful crawl is explainable after the fact.
* **The default domain allowlist is the start URL's *host* (plus its subdomains),
  not its registrable domain.** Deriving a registrable domain without a public
  suffix list is wrong in exactly the dangerous direction — `example.co.uk` would
  reduce to `co.uk` and authorise crawling the entire UK commercial namespace.
  A `www.` prefix is the one special case that is widened (to the apex domain),
  because that split is near-universal. Admins can pass `allowed_domains`
  explicitly to widen it further.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.rag.net import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    FetchError,
    NetPolicy,
    UnsafeURLError,
    assert_scheme_and_host,
    create_safe_client,
    safe_fetch,
)
from app.rag.sanitize import parse_html

logger = logging.getLogger("rag.crawler")

DEFAULT_MAX_DEPTH = 1
MAX_DEPTH_CAP = 3
DEFAULT_MAX_PAGES = 25
MAX_PAGES_CAP = 100

#: Per-page text cap. A single page contributing more than this is almost always a
#: dump/archive page, and embedding it would dominate the whole source.
DEFAULT_MAX_TEXT_CHARS = 100_000

#: Query parameters dropped during normalization: they identify a *visit*, not a
#: document, so keeping them would crawl the same page many times over.
TRACKING_PARAMS = frozenset(
    {
        "gclid",
        "fbclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "yclid",
        "dclid",
        "twclid",
        "ref",
        "ref_src",
        "_ga",
        "_gl",
        "spm",
    }
)

_DEFAULT_PORTS = {"http": 80, "https": 443}


class CrawlError(RuntimeError):
    """The crawl could not be started (the seed URL itself was unusable)."""


@dataclass(frozen=True)
class CrawlConfig:
    """Crawl limits. Values are clamped to their hard caps on construction."""

    max_depth: int = DEFAULT_MAX_DEPTH
    max_pages: int = DEFAULT_MAX_PAGES
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    allowed_domains: tuple[str, ...] = ()
    max_bytes: int = DEFAULT_MAX_BYTES
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS
    respect_robots: bool = True
    request_delay: float = 0.0
    #: Test-only escape hatch, threaded through to `NetPolicy`. Never set by a
    #: request handler or job.
    allow_private_addresses: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "max_depth", max(0, min(int(self.max_depth), MAX_DEPTH_CAP))
        )
        object.__setattr__(
            self, "max_pages", max(1, min(int(self.max_pages), MAX_PAGES_CAP))
        )
        object.__setattr__(self, "timeout", max(1.0, min(float(self.timeout), 60.0)))
        object.__setattr__(
            self,
            "allowed_domains",
            tuple(
                sorted(
                    {
                        d.strip().lower().lstrip(".")
                        for d in self.allowed_domains
                        if d.strip()
                    }
                )
            ),
        )

    def to_dict(self) -> dict[str, object]:
        """Serializable form, stored in `rag_sources.config`."""
        return {
            "max_depth": self.max_depth,
            "max_pages": self.max_pages,
            "timeout": self.timeout,
            "allowed_domains": list(self.allowed_domains),
            "respect_robots": self.respect_robots,
        }


@dataclass(frozen=True)
class CrawledPage:
    """One successfully fetched, de-fanged page."""

    url: str
    normalized_url: str
    title: str | None
    depth: int
    text: str
    content_checksum: str

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "normalized_url": self.normalized_url,
            "title": self.title,
            "depth": self.depth,
            "text": self.text,
            "content_checksum": self.content_checksum,
        }


@dataclass
class CrawlResult:
    """Pages plus the diagnostics needed to explain a partial crawl."""

    pages: list[CrawledPage] = field(default_factory=list)
    #: normalized_url -> reason (robots, duplicate content, empty, out of scope)
    skipped: dict[str, str] = field(default_factory=dict)
    #: normalized_url -> error message
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def stats(self) -> dict[str, object]:
        return {
            "pages": len(self.pages),
            "skipped": len(self.skipped),
            "errors": len(self.errors),
            "error_detail": dict(list(self.errors.items())[:10]),
            "skip_detail": dict(list(self.skipped.items())[:10]),
        }


def normalize_url(url: str) -> str:
    """Canonical form used for dedupe.

    Lowercases scheme/host, drops the default port, drops the fragment, removes
    known tracking parameters, and sorts what remains so `?b=2&a=1` and `?a=1&b=2`
    are one URL. Path case is preserved — paths are case-sensitive on most servers.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()

    netloc = host
    if parts.port and parts.port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{parts.port}"

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS and not key.lower().startswith("utm_")
    ]
    query = urlencode(sorted(query_pairs))

    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


def default_allowed_domains(start_url: str) -> tuple[str, ...]:
    """The conservative default allowlist for a seed URL (see module docstring)."""
    _scheme, host, _port = assert_scheme_and_host(start_url)
    host = host.lower()
    domains = {host}
    if host.startswith("www.") and host.count(".") >= 2:
        domains.add(host[4:])
    return tuple(sorted(domains))


def is_in_scope(url: str, allowed_domains: tuple[str, ...]) -> bool:
    """True if `url`'s host is, or is a subdomain of, an allowed domain."""
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return False
    return any(
        host == domain or host.endswith(f".{domain}") for domain in allowed_domains
    )


def content_checksum(text: str) -> str:
    """Stable checksum of a page's extracted text, used for content-level dedupe."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _RobotsCache:
    """One robots.txt fetch + parse per origin, reused for the whole crawl.

    Fetch failures fail **open** (the crawl proceeds). The alternative — refusing
    to crawl a site whose robots.txt 500s — would make the feature unusable on a
    meaningful fraction of the web, and the request is initiated by an
    authenticated admin who explicitly chose this URL, not by an anonymous user.
    """

    def __init__(self, policy: NetPolicy, client) -> None:
        self._policy = policy
        self._client = client
        self._parsers: dict[str, RobotFileParser | None] = {}

    async def _parser_for(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._parsers:
            return self._parsers[origin]

        robots_url = f"{origin}/robots.txt"
        parser: RobotFileParser | None = None
        try:
            response = await safe_fetch(
                robots_url,
                policy=self._policy,
                client=self._client,
                # Servers serve robots.txt as text/plain, text/html, or with no
                # type at all; the size/redirect/address guards still apply.
                allowed_content_types=frozenset(),
            )
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
        except (UnsafeURLError, FetchError) as exc:
            logger.info("no usable robots.txt at %s (%s); proceeding", robots_url, exc)
            parser = None

        self._parsers[origin] = parser
        return parser

    async def can_fetch(self, url: str) -> bool:
        parser = await self._parser_for(url)
        if parser is None:
            return True
        return parser.can_fetch("*", url)

    async def crawl_delay(self, url: str) -> float:
        parser = await self._parser_for(url)
        if parser is None:
            return 0.0
        try:
            delay = parser.crawl_delay("*")
        except Exception:  # pragma: no cover - defensive, parser is third-party
            return 0.0
        # Capped: a site advertising Crawl-delay: 3600 would otherwise hang a job.
        return min(float(delay), 2.0) if delay else 0.0


async def crawl(start_url: str, config: CrawlConfig | None = None) -> CrawlResult:
    """Breadth-first crawl from `start_url`, honouring every limit in `config`.

    Raises `CrawlError` if the seed URL itself cannot be fetched — a link source
    whose own URL is unreachable should fail loudly, not succeed with zero pages.
    Per-page failures below the seed are recorded in `CrawlResult.errors` instead.
    """
    config = config or CrawlConfig()

    try:
        assert_scheme_and_host(start_url)
    except UnsafeURLError as exc:
        raise CrawlError(str(exc)) from exc

    allowed_domains = config.allowed_domains or default_allowed_domains(start_url)

    policy = NetPolicy(
        timeout=config.timeout,
        max_bytes=config.max_bytes,
        allow_private_addresses=config.allow_private_addresses,
    )

    result = CrawlResult()
    seen_urls: set[str] = set()
    seen_checksums: dict[str, str] = {}

    start_normalized = normalize_url(start_url)
    queue: deque[tuple[str, str, int]] = deque([(start_url, start_normalized, 0)])
    seen_urls.add(start_normalized)

    client = create_safe_client(policy)
    robots = _RobotsCache(policy, client)

    try:
        while queue and len(result.pages) < config.max_pages:
            url, normalized, depth = queue.popleft()
            is_seed = normalized == start_normalized

            if config.respect_robots and not await robots.can_fetch(url):
                message = "disallowed by robots.txt"
                if is_seed:
                    raise CrawlError(f"{url} is {message}")
                result.skipped[normalized] = message
                continue

            delay = config.request_delay or (
                await robots.crawl_delay(url) if config.respect_robots else 0.0
            )
            if delay:
                await asyncio.sleep(delay)

            try:
                response = await safe_fetch(url, policy=policy, client=client)
            except (UnsafeURLError, FetchError) as exc:
                if is_seed:
                    raise CrawlError(f"could not fetch {url}: {exc}") from exc
                result.errors[normalized] = str(exc)
                continue

            final_normalized = normalize_url(response.url)
            if final_normalized != normalized and final_normalized in seen_urls:
                # A redirect landed us somewhere already crawled.
                result.skipped[normalized] = (
                    f"redirected to already-seen {final_normalized}"
                )
                continue
            seen_urls.add(final_normalized)

            if response.content_type == "text/plain":
                parsed_text = response.text.strip()
                title, links = None, ()
            else:
                parsed = parse_html(response.text, base_url=response.url)
                parsed_text, title, links = parsed.text, parsed.title, parsed.links

            text = parsed_text[: config.max_text_chars]
            if not text.strip():
                result.skipped[final_normalized] = "no extractable text"
                continue

            checksum = content_checksum(text)
            if checksum in seen_checksums:
                result.skipped[final_normalized] = (
                    f"duplicate content of {seen_checksums[checksum]}"
                )
                continue
            seen_checksums[checksum] = final_normalized

            result.pages.append(
                CrawledPage(
                    url=response.url,
                    normalized_url=final_normalized,
                    title=title,
                    depth=depth,
                    text=text,
                    content_checksum=checksum,
                )
            )

            if depth >= config.max_depth:
                continue

            for link in links:
                link_normalized = normalize_url(link)
                if link_normalized in seen_urls:
                    continue
                if not is_in_scope(link_normalized, allowed_domains):
                    result.skipped.setdefault(
                        link_normalized, "outside allowed domains"
                    )
                    continue
                seen_urls.add(link_normalized)
                queue.append((link, link_normalized, depth + 1))

                # Bound the frontier: anything beyond max_pages can never be
                # crawled anyway, and an unbounded queue on a link-farm page is
                # its own small denial-of-service.
                if len(seen_urls) > config.max_pages * 10:
                    break
    finally:
        await client.aclose()

    logger.info(
        "crawl of %s finished: %d page(s), %d skipped, %d error(s)",
        start_url,
        len(result.pages),
        len(result.skipped),
        len(result.errors),
    )
    return result
