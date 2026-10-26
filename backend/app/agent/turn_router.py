"""Turn router: fills in a lookup's arguments so it can run before the LLM.

A lookup turn used to cost the LLM two round trips: one to pick the tool and its
arguments, one to answer from the result. Jev already judges every finished
turn and, with the router on, says which lookup it needs (turn_judge.LOOKUP_KEY).
Jev can only answer typed questions, not write arguments, so this small, fast
LLM call -- started alongside Jev -- extracts them as JSON. The gate then runs
the search and hands the result to the LLM as if it had called the tool itself,
leaving it one round trip.

Kept free of livekit imports so scripts/router_bench can drive the exact request
the agent sends.
"""

import asyncio
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field

import httpx

from app.agent.turn_judge import Exchange

logger = logging.getLogger(__name__)
# Same logger as app.agent.usage_log, so all provider usage lines filter together.
usage_logger = logging.getLogger("agent.usage")

_SYSTEM = """You fill in the arguments of a mobile operator's package search from a \
conversation with a customer in Bangladesh. The customer speaks Bangla, English or both. \
Fill both fields for the customer's latest message; the caller decides which one runs.

packages -- arguments for searching the operator's packages:
- Use only criteria the customer has stated or confirmed in this conversation: the \
latest message plus the earlier ones, unless they've since changed it. Leave everything \
else null. Never invent a criterion, and never take one from what the assistant said (a \
pack it described is not something the customer asked for).
- kind: "data" for internet / data / ডাটা / নেট packs, "voice" for minutes / talk-time / \
মিনিট packs, "bundle" for combo packs with data and minutes together, "sms" for SMS packs.
- max_price: plain number in taka, the most they want to pay ("৩০০ টাকার মধ্যে" -> 300, \
"under 500" -> 500, "এক হাজার" -> 1000).
- min_data_gb: the least data they want, in GB as a number ("10 GB" -> 10, "৫০০ এমবি" -> 0.5).
- validity_days: how long the pack should last in days ("7 din" -> 7, "এক মাস" -> 30, \
"সাপ্তাহিক" -> 7).

knowledge_query: the latest message as a short English search query about the operator's \
services, policies, coverage or how something works, or null."""

_NULLABLE_STRING = {"type": ["string", "null"]}
_NULLABLE_NUMBER = {"type": ["number", "null"]}
_NULLABLE_INTEGER = {"type": ["integer", "null"]}

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["packages", "knowledge_query"],
    "properties": {
        "packages": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "max_price", "min_data_gb", "validity_days"],
            "properties": {
                "kind": {
                    "type": ["string", "null"],
                    "enum": ["data", "voice", "bundle", "sms", None],
                },
                "max_price": _NULLABLE_NUMBER,
                "min_data_gb": _NULLABLE_NUMBER,
                "validity_days": _NULLABLE_INTEGER,
            },
        },
        "knowledge_query": _NULLABLE_STRING,
    },
}


@dataclass(frozen=True)
class RouterArgs:
    """Arguments for each lookup, with unset (null) ones left out."""

    packages: dict = field(default_factory=dict)
    knowledge_query: str | None = None


# ---- fast rules ----
#
# A plain package request ("৩০০ টাকার মধ্যে ১০ জিবি ইন্টারনেট প্যাক", "weekly voice
# packs under 100 taka") needs no model: these rules read it in well under a
# millisecond, the way _SYSTEM tells the extractor to. They answer only when they
# understand every word and no earlier customer message could add a criterion.
# Anything else -- a word they don't know, a negation ("ছাড়া"), a number with no
# unit, an amount with no "under" beside it ("৩০০ টাকার প্যাক": a ceiling or a
# rough price?) -- returns None, and the extractor answers as before.


def _nfc(text: str) -> str:
    # য়, ড় and ঢ় each have two encodings; NFC spells both the same.
    return unicodedata.normalize("NFC", text)


@dataclass(frozen=True)
class _Tok:
    kind: str
    value: object = None
    # Said as a word ("তিন", "seven"), not digits.
    word: bool = False


_WORDS: list[tuple[str, object, str]] = [
    ("kind", "data", "ডাটা ডেটা ইন্টারনেট নেট data internet net"),
    ("kind", "voice", "মিনিট টকটাইম minute minutes min mins voice talktime"),
    ("kind", "bundle", "কম্বো বান্ডেল combo bundle"),
    ("kind", "sms", "এসএমএস sms"),
    ("pack", None, "প্যাক প্যাকেজ pack packs package packages"),
    ("gb", 1.0, "জিবি gb"),
    ("gb", 0.001, "এমবি mb"),
    ("days", 1, "দিন দিনের day days din diner"),
    ("days", 7, "সপ্তাহ সপ্তাহের week weeks"),
    ("days", 30, "মাস মাসের month months mash"),
    # A period on its own: one of it.
    ("period", 7, "সাপ্তাহিক weekly"),
    ("period", 30, "মাসিক monthly"),
    ("taka", None, "টাকা টাকার taka takar tk taka's"),
    ("max", None, "মধ্যে নিচে ভিতরে under below within upto max maximum moddhe niche"),
    ("unit", 1000, "হাজার thousand hajar"),
    ("num", 1, "এক একটা একটি one ek"),
    ("num", 2, "দুই দু two dui"),
    ("num", 3, "তিন three tin"),
    ("num", 4, "চার four char"),
    ("num", 5, "পাঁচ five pach"),
    ("num", 6, "ছয় six choy"),
    ("num", 7, "সাত seven sat"),
    ("num", 8, "আট eight"),
    ("num", 10, "দশ ten dosh"),
    ("num", 12, "বারো twelve"),
    ("num", 15, "পনেরো পনের fifteen"),
    ("num", 20, "বিশ twenty"),
    ("num", 25, "পঁচিশ"),
    ("num", 30, "ত্রিশ তিরিশ thirty"),
    ("num", 50, "পঞ্চাশ fifty"),
    ("num", 100, "একশো একশ hundred"),
    ("num", 200, "দুইশো দুশো"),
    ("num", 300, "তিনশো তিনশ"),
    ("num", 500, "পাঁচশো পাঁচশ"),
    # Words that add nothing to a search.
    (
        "filler",
        None,
        "আমি আমার আমাকে কি কী কোনো কোন কোনটা আছে আছেন দেখান দেখাও দিন দেন চাই চাচ্ছি "
        "লাগবে দরকার নিতে নেব জন্য এর র এ তে টা টি গুলো গুলা হবে হলে ভালো আচ্ছা জি একটু "
        "প্লিজ ভাই আপু স্যার কিছু কয়টা সব বলেন বলুন জানান থাকলে পাওয়া যাবে যায় "
        "i im me my we a an any some the show tell give want need looking look for find "
        "please do you have is there are available what which with of in at to me can could "
        "ache dekhao dao chai lagbe amar ki kono er jonno ekta hi hello ok okay so",
    ),
]

_LEXICON: dict[str, _Tok] = {
    _nfc(word): _Tok(kind, value, word=kind == "num")
    for kind, value, words in _WORDS
    for word in words.split()
}

# Bangla case endings, longest first ("জিবির" -> জিবি, "প্যাকগুলো" -> প্যাক).
_BN_SUFFIXES = tuple(
    sorted(
        {_nfc(s) for s in ("গুলোর", "গুলো", "টার", "টির", "য়ের", "ের", "এর", "তে", "টা", "টি", "র", "ে")},
        key=len,
        reverse=True,
    )
)

_TO_ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_DIGITS_RE = re.compile(_nfc(r"^(\d+(?:\.\d+)?)(?:টা|টি|টার|টির)?$"))

_PHRASES = [
    # "10GB", "৫০০এমবি", "৩০দিন": the number and its unit apart.
    (re.compile(r"(\d)([^\d\s.,])"), r"\1 \2"),
    (re.compile(r"\bup\s*to\b"), " upto "),
    (re.compile(r"\bless\s+than\b"), " under "),
    (re.compile(r"\btalk\s*time\b"), " talktime "),
    (re.compile(_nfc(r"টক\s*টাইম")), " টকটাইম "),
]


def _tokens(utterance: str) -> list[_Tok] | None:
    """The utterance as lexicon words, or None if any word isn't one."""
    text = _nfc(utterance).translate(_TO_ASCII_DIGITS).lower()
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    text = re.sub(r"['’\"“”]", "", text)
    for pattern, repl in _PHRASES:
        text = pattern.sub(repl, text)
    text = re.sub(r"[,;:!?।॥()\[\]/\-–—]|(?<!\d)\.|\.(?!\d)", " ", text)
    out: list[_Tok] = []
    for raw in text.split():
        tok = _token(raw)
        if tok is None:
            return None
        out.append(tok)
    return out


def _token(raw: str) -> _Tok | None:
    if m := _DIGITS_RE.match(raw):
        return _Tok("num", float(m.group(1)))
    if tok := _LEXICON.get(raw):
        return tok
    for suffix in _BN_SUFFIXES:
        if raw.endswith(suffix) and len(raw) > len(suffix):
            if tok := _LEXICON.get(raw[: -len(suffix)]):
                return tok
    return None


def _package_criteria(utterance: str) -> dict | None:
    """The package search the utterance states on its own, in the extractor's
    shape (unset ones left out), or None unless every word is understood."""
    toks = _tokens(utterance)
    if toks is None:
        return None
    n = len(toks)

    def kind_at(j: int) -> str | None:
        return toks[j].kind if j < n else None

    search: dict = {}
    price: float | None = None
    capped = pack = False
    i = 0
    while i < n:
        tok = toks[i]
        k = tok.kind
        if k == "num":
            value = float(tok.value)
            j = i + 1
            if kind_at(j) == "unit":
                value *= float(toks[j].value)
                j += 1
            nxt = kind_at(j)
            if nxt == "gb":
                if "min_data_gb" in search:
                    return None
                search["min_data_gb"] = round(value * float(toks[j].value), 3)
            elif nxt == "days":
                if "validity_days" in search or value != int(value):
                    return None
                search["validity_days"] = int(value) * int(toks[j].value)
            elif nxt == "taka":
                if price is not None:
                    return None
                price = value
            elif tok.word and value == 1 and nxt in ("kind", "pack", "period"):
                # "একটা ডাটা প্যাক", "one data pack": an article, not a number.
                i += 1
                continue
            else:
                # A number with no unit: a price, an amount of data, a count?
                return None
            i = j + 1
            continue
        if k == "kind":
            if search.get("kind") not in (None, tok.value):
                return None
            search["kind"] = tok.value
        elif k == "period":
            if "validity_days" in search:
                return None
            search["validity_days"] = tok.value
        elif k == "pack":
            pack = True
        elif k == "max":
            capped = True
        elif k != "filler":
            # A unit, "days" or "taka" with no number before it.
            return None
        i += 1

    if price is not None:
        if not capped:
            return None
        search["max_price"] = price
    # Without a pack word or a pack kind it may not be a package search at all
    # ("৫০০ টাকা" alone is likely a recharge).
    if not (pack or "kind" in search):
        return None
    return search or None


def fast_extract(utterance: str, history: list[Exchange] | None = None) -> RouterArgs | None:
    """The package search for a plain request, or None to ask the extractor:
    also when an earlier customer message might hold a criterion the
    extractor would carry over ("সাত দিনের মধ্যে হলে?" after a pack search)."""
    if any(e.role == "user" and _mentions_package(e.text) for e in history or ()):
        return None
    search = _package_criteria(utterance)
    return RouterArgs(packages=search) if search else None


def _mentions_package(text: str) -> bool:
    """Any digit or package word: what the extractor might carry over."""
    plain = _nfc(text).translate(_TO_ASCII_DIGITS).lower()
    if re.search(r"\d", plain):
        return True
    for raw in re.split(r"[\s,;:!?।॥.()\[\]/\-–—]+", plain):
        tok = _token(raw) if raw else None
        if tok is not None and tok.kind in ("kind", "pack", "gb", "days", "period", "taka"):
            return True
    return False


def build_request(
    model: str,
    history: list[Exchange],
    utterance: str,
    reasoning_effort: str = "none",
) -> dict:
    """reasoning_effort: an extraction needs none, and every reasoning token is
    latency; a model that can't turn reasoning off fails the request (the LLM
    then calls the tools itself)."""
    lines = ["Conversation so far:"]
    lines += [f"{'Customer' if e.role == 'user' else 'Assistant'}: {e.text}" for e in history]
    if not history:
        lines.append("(none yet)")
    lines.append(f"Customer's latest message: {utterance}")
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "\n".join(lines)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "lookup_arguments", "strict": True, "schema": _SCHEMA},
        },
        # No temperature: OpenAI's reasoning models reject it, and with
        # require_parameters that leaves no endpoint at all.
        "max_tokens": 200,
        "reasoning": {"effort": reasoning_effort},
        # require_parameters: never routed to a provider that would ignore
        # response_format; sort: the fastest one. Customer speech: keep it out of
        # provider training data.
        "provider": {
            "require_parameters": True,
            "sort": "latency",
            "data_collection": "deny",
        },
    }


def parse(content: str) -> RouterArgs | None:
    """The model's JSON, with nulls dropped; None if it isn't the expected shape."""
    try:
        data = json.loads(content)
        packages = {k: v for k, v in data["packages"].items() if v not in (None, "")}
        query = data.get("knowledge_query") or None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if query is not None and not isinstance(query, str):
        return None
    return RouterArgs(packages=packages, knowledge_query=query)


async def extract(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    payload: dict,
    timeout_s: float,
) -> RouterArgs | None:
    """The lookup arguments for the turn, or None on any error or timeout (the
    LLM then calls the tools itself, as without the router)."""
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            ),
            timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        cost = usage.get("cost")
        usage_logger.info(
            "Router %s: %s input tokens, %s output, $%s, %dms",
            body.get("model") or payload.get("model"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            f"{cost:.6f}" if isinstance(cost, (int, float)) else "?",
            (time.perf_counter() - started) * 1000,
        )
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("turn router timed out after %.2fs", timeout_s)
        return None
    except Exception as exc:
        logger.warning("turn router failed: %s", exc)
        return None
    args = parse(content) if isinstance(content, str) else None
    if args is None:
        logger.warning("turn router returned unusable arguments: %r", content)
    return args
