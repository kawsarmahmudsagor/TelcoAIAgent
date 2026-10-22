"""SSRF-hardened outbound HTTP.

Everything the RAG link crawler fetches is a URL an admin typed in, which makes it
an attacker-influenced request originating *inside* our network. This module is the
only sanctioned way to make such a request.

What it enforces:

* **Scheme allowlist** — `http` / `https` only. No `file:`, `gopher:`, `ftp:`.
* **Address filtering** — the hostname is resolved up front and *every* address it
  resolves to is checked against loopback / private / link-local / CGNAT /
  multicast / reserved ranges, plus an explicit deny of `169.254.169.254` (the
  cloud instance-metadata endpoint, the classic SSRF prize). IPv4-mapped and
  6to4/Teredo-embedded IPv6 addresses are unwrapped and re-checked, so
  `::ffff:127.0.0.1` cannot sneak a loopback address past the filter.
* **Redirects are followed manually.** httpx's `follow_redirects=True` would
  perform the intermediate requests itself, which means our address check would
  only ever have run against the *first* hop — a server can answer the initial
  (public, passing) request with `Location: http://169.254.169.254/...`. So
  redirects are disabled at the transport level and re-driven here, re-running the
  full validation on every hop, with a hard hop limit.
* **Size limit** — `Content-Length` is rejected early when it is present and too
  large, and the body is streamed with a running byte count so a missing or lying
  header still can't blow up memory.
* **Timeout** — a total per-request timeout, applied to each hop.
* **Content-Type allowlist** — only the text types the crawler can actually parse.

Known residual risk (documented, not fixed): between our `getaddrinfo` check and
httpx's own resolution there is a TOCTOU window in which a DNS record with a tiny
TTL could flip from a public address to a private one ("DNS rebinding"). Closing it
properly means pinning the connection to the already-validated IP while preserving
SNI/Host, which needs a custom transport. Given the caller is an authenticated
admin adding a knowledge-base source (not an anonymous user), the pre-connect and
per-redirect checks are the agreed level of defence here.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpx

logger = logging.getLogger("app.rag.net")

ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Content types the crawler knows how to turn into text.
DEFAULT_ALLOWED_CONTENT_TYPES = frozenset(
    {"text/html", "text/plain", "application/xhtml+xml"}
)

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_BYTES = 2 * 1024 * 1024  # 2 MB
DEFAULT_MAX_REDIRECTS = 5

USER_AGENT = "RealEstateAgentBot/1.0 (+knowledge-base crawler)"

# Cloud instance metadata services. Both are inside ranges we block anyway; they
# are listed separately so the rejection message names the actual threat.
METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),  # AWS/Azure/GCP/DO IMDS
        ipaddress.ip_address("fd00:ec2::254"),  # AWS IMDSv6
    }
)

# Carrier-grade NAT. Python's `is_private` stopped covering this range in newer
# 3.x releases, so it is checked explicitly rather than relied upon.
_CGNAT_V4 = ipaddress.ip_network("100.64.0.0/10")


class UnsafeURLError(ValueError):
    """The URL is not allowed to be fetched (scheme, DNS, or address policy)."""


class FetchError(RuntimeError):
    """The fetch failed for a transport/protocol reason."""


class TooManyRedirectsError(FetchError):
    """The redirect chain exceeded the hop limit."""


class ResponseTooLargeError(FetchError):
    """The response body exceeded the configured size limit."""


class DisallowedContentTypeError(FetchError):
    """The response's Content-Type is not in the allowlist."""


@dataclass(frozen=True)
class NetPolicy:
    """Knobs for `safe_fetch`, grouped so the crawler can pass one object around.

    `allow_private_addresses` exists **only** so the test-suite can point the very
    same code path at a loopback fixture server. It must never be enabled from a
    request handler; nothing in app.api or app.rag.jobs sets it.
    """

    timeout: float = DEFAULT_TIMEOUT_SECONDS
    max_bytes: int = DEFAULT_MAX_BYTES
    max_redirects: int = DEFAULT_MAX_REDIRECTS
    allowed_content_types: frozenset[str] = DEFAULT_ALLOWED_CONTENT_TYPES
    allow_private_addresses: bool = False
    user_agent: str = USER_AGENT
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SafeResponse:
    """A fully-read, size-capped response from `safe_fetch`."""

    url: str
    """The final URL after redirects."""
    status_code: int
    content_type: str
    content: bytes
    encoding: str | None = None
    redirect_chain: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")


def _unwrap_ipv6(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """Return the IPv4 address embedded in a mapped/6to4/Teredo IPv6 address."""
    for attribute in ("ipv4_mapped", "sixtofour", "teredo"):
        value = getattr(address, attribute, None)
        if attribute == "teredo" and value is not None:
            # `teredo` is a (server, client) pair; the client side is the one that
            # would actually be reached.
            return value[1]
        if value is not None:
            return value
    return None


def is_blocked_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if `address` is in a range we refuse to connect to."""
    if address in METADATA_ADDRESSES:
        return True

    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return True

    if isinstance(address, ipaddress.IPv4Address):
        return address in _CGNAT_V4

    if getattr(address, "is_site_local", False):
        return True

    embedded = _unwrap_ipv6(address)
    if embedded is not None:
        return is_blocked_address(embedded)

    return False


def assert_scheme_and_host(url: str) -> tuple[str, str, int | None]:
    """Validate the URL's shape. Returns `(scheme, hostname, port)`."""
    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(
            f"scheme {scheme or '(none)'!r} is not allowed; "
            f"only {', '.join(sorted(ALLOWED_SCHEMES))} are"
        )

    hostname = parts.hostname
    if not hostname:
        raise UnsafeURLError(f"URL has no host: {url!r}")

    try:
        port = parts.port
    except ValueError as exc:  # malformed port, e.g. http://h:notaport/
        raise UnsafeURLError(f"invalid port in URL {url!r}") from exc

    return scheme, hostname, port


async def resolve_allowed_addresses(
    hostname: str,
    port: int,
    *,
    allow_private_addresses: bool = False,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve `hostname` and raise `UnsafeURLError` if *any* address is blocked.

    Any-match (rather than all-match) is deliberate: a host that resolves to both a
    public and a private address is exactly the DNS-rebinding shape we are refusing.
    """
    # A bare IP literal in the URL never reaches DNS, but must still be checked.
    try:
        literal = ipaddress.ip_address(hostname.strip("[]"))
    except ValueError:
        literal = None

    if literal is not None:
        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [literal]
    else:
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.getaddrinfo(
                hostname, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
        except socket.gaierror as exc:
            raise UnsafeURLError(f"could not resolve host {hostname!r}: {exc}") from exc

        addresses = []
        for info in infos:
            sockaddr = info[4]
            try:
                addresses.append(ipaddress.ip_address(sockaddr[0]))
            except ValueError:  # pragma: no cover - getaddrinfo shouldn't do this
                continue

    if not addresses:
        raise UnsafeURLError(f"host {hostname!r} resolved to no usable addresses")

    if allow_private_addresses:
        return addresses

    for address in addresses:
        if address in METADATA_ADDRESSES:
            raise UnsafeURLError(
                f"host {hostname!r} resolves to the cloud metadata endpoint "
                f"({address}); refusing to connect"
            )
        if is_blocked_address(address):
            raise UnsafeURLError(
                f"host {hostname!r} resolves to non-public address {address}; "
                "refusing to connect"
            )

    return addresses


async def assert_url_allowed(url: str, *, allow_private_addresses: bool = False) -> str:
    """Full pre-connect validation of a single URL. Returns the URL unchanged."""
    scheme, hostname, port = assert_scheme_and_host(url)
    await resolve_allowed_addresses(
        hostname,
        port or (443 if scheme == "https" else 80),
        allow_private_addresses=allow_private_addresses,
    )
    return url


def create_safe_client(policy: NetPolicy | None = None) -> httpx.AsyncClient:
    """An `httpx.AsyncClient` configured the way `safe_fetch` needs it.

    Callers that fetch many URLs (the crawler) should create one client and pass it
    to `safe_fetch` so connections are pooled. `follow_redirects` is forced off:
    redirect handling lives in `safe_fetch`, which re-validates every hop.
    """
    policy = policy or NetPolicy()
    headers = {
        "User-Agent": policy.user_agent,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
        "Accept-Encoding": "gzip, deflate",
        **policy.extra_headers,
    }
    return httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(policy.timeout),
        headers=headers,
        # Bounded so one crawl can't exhaust sockets.
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        trust_env=False,  # ignore ambient proxy env vars
    )


def _type_allowed(media_type: str, allowed: frozenset[str]) -> bool:
    """Exact match, or a `family/*` entry (e.g. `image/*`) covering the whole family."""
    if media_type in allowed:
        return True
    family = media_type.split("/", 1)[0]
    return bool(family) and f"{family}/*" in allowed


def _media_type(content_type_header: str | None) -> str:
    return (content_type_header or "").split(";", 1)[0].strip().lower()


async def _read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    """Stream the body, aborting as soon as it exceeds `max_bytes`."""
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > max_bytes:
                raise ResponseTooLargeError(
                    f"Content-Length {declared} exceeds the {max_bytes} byte limit"
                )
        except ValueError:
            pass  # unparseable header; the streaming cap below still applies

    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ResponseTooLargeError(
                f"response body exceeded the {max_bytes} byte limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def safe_fetch(
    url: str,
    *,
    policy: NetPolicy | None = None,
    client: httpx.AsyncClient | None = None,
    allowed_content_types: frozenset[str] | None = None,
    headers: dict[str, str] | None = None,
) -> SafeResponse:
    """GET `url` with every SSRF guard in this module applied.

    `headers` (e.g. a bearer token) are sent only while the request stays on
    `url`'s own host: a redirect to another host gets none of them, so a
    credential never leaks to a server it wasn't meant for.

    Raises `UnsafeURLError` for a policy violation (including on any redirect hop)
    and a `FetchError` subclass for transport/size/content-type problems.
    """
    policy = policy or NetPolicy()
    allowed_types = (
        allowed_content_types
        if allowed_content_types is not None
        else policy.allowed_content_types
    )

    owns_client = client is None
    client = client or create_safe_client(policy)

    chain: list[str] = []
    current = url
    origin_host = (urlsplit(url).hostname or "").lower()
    try:
        for hop in range(policy.max_redirects + 1):
            # Re-validated on EVERY hop; this is the whole point of not letting
            # httpx follow redirects itself.
            await assert_url_allowed(
                current, allow_private_addresses=policy.allow_private_addresses
            )

            same_host = (urlsplit(current).hostname or "").lower() == origin_host
            request = client.build_request(
                "GET", current, headers=headers if headers and same_host else None
            )
            try:
                response = await client.send(request, stream=True)
            except httpx.HTTPError as exc:
                raise FetchError(f"request to {current} failed: {exc}") from exc

            try:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError(
                            f"{current} returned {response.status_code} "
                            "with no Location header"
                        )
                    next_url = urljoin(str(response.url), location)
                    if hop >= policy.max_redirects:
                        raise TooManyRedirectsError(
                            f"exceeded {policy.max_redirects} redirects starting at {url}"
                        )
                    chain.append(current)
                    logger.debug("redirect %s -> %s", current, next_url)
                    current = next_url
                    continue

                if response.status_code >= 400:
                    raise FetchError(f"{current} returned HTTP {response.status_code}")

                media_type = _media_type(response.headers.get("content-type"))
                if allowed_types and not _type_allowed(media_type, allowed_types):
                    raise DisallowedContentTypeError(
                        f"{current} returned content-type {media_type or '(none)'!r}; "
                        f"allowed: {', '.join(sorted(allowed_types))}"
                    )

                body = await _read_capped(response, policy.max_bytes)
                return SafeResponse(
                    url=str(response.url),
                    status_code=response.status_code,
                    content_type=media_type,
                    content=body,
                    encoding=response.charset_encoding,
                    redirect_chain=tuple(chain),
                )
            finally:
                await response.aclose()

        raise TooManyRedirectsError(  # pragma: no cover - loop above always returns
            f"exceeded {policy.max_redirects} redirects starting at {url}"
        )
    finally:
        if owns_client:
            await client.aclose()
