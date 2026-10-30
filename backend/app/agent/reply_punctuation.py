"""Dashes and semicolons out of the agent's replies, and "package" for "pack".

The prompt asks for no colons, semicolons or dashes, but the model still writes
"...২ ঘণ্টার মধ্যে চালু হয়—চাইলে...". An em or en dash, or a semicolon,
becomes a comma here, in the LLM's stream, so the chat transcript, the chat
context and the TTS all get the same text. A hyphen is left alone: it is in
pack codes and references (D8-7D, TC-2048), and a dash between two digits is a
range (২–৩), kept as a hyphen.

The agent always says "package" (প্যাকেজ), never "pack" (প্যাক): the prompt
says so, but a tool's text or a KB passage can still lead the model to it. A
slow connection is "স্লো", the word people say, not the bookish ধীর.
"""

import re
from collections.abc import AsyncIterable
from typing import Any

from livekit.agents import llm

_DIGIT = r"[0-9০-৯]"
_RANGE_RE = re.compile(rf"(?<={_DIGIT})\s*[—–]\s*(?={_DIGIT})")
_BREAK_RE = re.compile(r"\s*[—–;]\s*")


# প্যাক inside a compound ("ডাটাপ্যাক") or with a suffix ("প্যাকগুলো",
# "প্যাকে") too, but not প্যাকেজ, প্যাকেট (packet) or প্যাকিং (packing).
_PACK_BN_RE = re.compile("প্যাক(?!েজ|েট|িং)")
_PACK_EN_RE = re.compile(r"\b(pack)(s?)\b", re.IGNORECASE)


# ধীর, ধীরে, ধীরগতি(র/তে): স্লো. "ধীরে ধীরে" (gradually) stays.
_SLOW_BN_RE = re.compile(r"(?<!ধীরে )ধীর(?!ে\s*ধীরে)(?:\s*গতি(?:র|তে)?|ে)?")


def _package(m: re.Match[str]) -> str:
    word, plural = m.group(1), m.group(2)
    if word.isupper():
        return "PACKAGE" + plural.upper()
    return ("Package" if word[0].isupper() else "package") + plural


def clean_reply_text(text: str) -> str:
    text = _RANGE_RE.sub("-", text)
    text = _PACK_BN_RE.sub("প্যাকেজ", text)
    text = _PACK_EN_RE.sub(_package, text)
    text = _SLOW_BN_RE.sub("স্লো", text)
    return _BREAK_RE.sub(", ", text)


_TAIL_RE = re.compile(r"[\s—–;]*\Z")
# The start of a "pack" whose end is still to come: "প্যাক" may yet be
# প্যাকেজ, "pack" may yet be "package".
_PARTIAL_PACK_RE = re.compile(
    r"(?:(?<![A-Za-z])p(?:a(?:c(?:k(?:s)?)?)?)?|প(?:্(?:য(?:া(?:ক(?:ে|ি)?)?)?)?)?"
    # and a ধীর whose end ("ে", "গতি", "ধীরে ধীরে") is still to come
    r"|ধ(?:ী(?:র(?:ে)?)?)?)\Z",
    re.IGNORECASE,
)


class _Cleaner:
    """Streaming state. Text ending in spaces, a dash or a semicolon waits for
    the next chunk, which shows what the dash sits between, and so does a word
    that may be a "pack" (প্যা | ক); the last character sent is kept so a range
    split across chunks (২ | – ৩) is still seen."""

    def __init__(self) -> None:
        self._held = ""
        self._last = ""

    def feed(self, chunk: str) -> str:
        text = self._held + chunk
        cut = _TAIL_RE.search(text).start()
        if partial := _PARTIAL_PACK_RE.search(text[:cut]):
            cut = partial.start()
        self._held = text[cut:]
        return self._emit(text[:cut])

    def flush(self, *, end: bool = False) -> str:
        """Before a non-text chunk, or at the `end` of the reply (trailing
        spaces go too): a dangling dash or semicolon is dropped."""
        text, self._held = self._held, ""
        text = re.sub(r"[—–;]", "", text)
        return self._emit(text.rstrip() if end else text)

    def _emit(self, text: str) -> str:
        if not text:
            return ""
        out = clean_reply_text(self._last + text)[len(self._last):]
        self._last = out[-1:] or self._last
        return out


def _with_content(chunk: llm.ChatChunk, content: str) -> llm.ChatChunk:
    return chunk.model_copy(update={"delta": chunk.delta.model_copy(update={"content": content})})


async def clean_reply_stream(stream: AsyncIterable[Any]) -> AsyncIterable[Any]:
    """An llm_node stream with its text cleaned; tool calls and anything else
    pass through as they are."""
    cleaner = _Cleaner()
    async for chunk in stream:
        if isinstance(chunk, str):
            if out := cleaner.feed(chunk):
                yield out
        elif isinstance(chunk, llm.ChatChunk) and chunk.delta is not None and chunk.delta.content:
            out = cleaner.feed(chunk.delta.content)
            if out or chunk.delta.tool_calls:
                yield _with_content(chunk, out)
        else:
            if rest := cleaner.flush():
                yield rest
            yield chunk
    if rest := cleaner.flush(end=True):
        yield rest
