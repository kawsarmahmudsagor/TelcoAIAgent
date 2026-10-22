"""Shows the one listing a reply is about, in place of the whole shortlist.

On web sessions the agent opens a reply about a single shortlisted listing with
a hidden marker, "[show:N]" (N is the #number search_apartments gave it). The
marker is stripped from the reply stream before anything else sees it (TTS,
transcript, chat history), and that listing's card is sent to the browser on
LISTING_FOCUS_TOPIC, which shows it from the moment the reply is spoken.

When a reply has no marker, a fallback reads the finished reply text: if it
names exactly one shown listing, by its title or its price, that card is sent
instead. A reply naming several listings sends nothing.

Nothing is sent on a phone call, in a reply that ran a search or touched the
booking (the shortlist or the form is what belongs on screen then), or while
the booking form is on screen.
"""

import json
import logging
import re
from collections.abc import AsyncIterable
from typing import Any

from livekit.agents import llm

from app.agent.userdata import BookingState, SessionUserdata

logger = logging.getLogger("agent.listing_focus")

# Must match LISTING_FOCUS_TOPIC in frontend/lib/livekit-text-streams.ts.
LISTING_FOCUS_TOPIC = "listing-focus"

# "[show:2]", tolerating "[Show: #2]" and Bangla digits ("[show:২]").
# Its trailing space goes too, so the reply doesn't open with one.
_MARKER_RE = re.compile(r"\[\s*show\s*:\s*#?\s*(\d+)\s*\][ \t]*", re.I)
# A trailing "[" that may still grow into a marker in the next chunk.
_PARTIAL_RE = re.compile(r"\[\s*(?:s(?:h(?:o(?:w\s*(?::\s*#?\s*\d*\s*)?)?)?)?)?\Z", re.I)

# Tools after which the shortlist or the booking form is what the screen shows.
_SCREEN_TOOLS = frozenset(
    {"search_apartments", "update_booking_form", "book_appointment", "reschedule_viewing"}
)

# An amount as written in a reply: "40 lakh", "১৪,০০০", "1.2 crore", "১ কোটি ৬ লাখ".
_AMOUNT_RE = re.compile(
    r"(?<![\d,.])(?P<num>\d{1,3}(?:,\d{2,3})+|\d+)(?:\.(?P<frac>\d+))?"
    r"(?:\s*(?P<unit>crore|কোটি|lakh|lac|লাখ|লক্ষ|thousand|হাজার)(?![A-Za-zঀ-৿]))?",
    re.I,
)
_UNITS = {
    "crore": 10_000_000, "কোটি": 10_000_000,
    "lakh": 100_000, "lac": 100_000, "লাখ": 100_000, "লক্ষ": 100_000,
    "thousand": 1_000, "হাজার": 1_000,
}
# Bedrooms, sqft and the like are never this small a price.
_MIN_PRICE = 1_000


class MarkerStripper:
    """Removes "[show:N]" markers from streamed text, holding back a "[" only
    while it can still turn into one."""

    def __init__(self) -> None:
        self._buffer = ""
        self._started = False  # whether any text has gone out yet
        self.numbers: list[int] = []

    def feed(self, text: str) -> str:
        self._buffer = self._strip(self._buffer + text)
        partial = _PARTIAL_RE.search(self._buffer)
        cut = partial.start() if partial else len(self._buffer)
        out, self._buffer = self._buffer[:cut], self._buffer[cut:]
        return self._emit(out)

    def flush(self) -> str:
        out, self._buffer = self._strip(self._buffer), ""
        return self._emit(out)

    def _emit(self, text: str) -> str:
        # The reply doesn't open with the space a marker left behind.
        if not self._started:
            text = text.lstrip()
            self._started = bool(text)
        return text

    def _strip(self, text: str) -> str:
        def keep(match: re.Match) -> str:
            self.numbers.append(int(match.group(1)))
            return ""

        return _MARKER_RE.sub(keep, text)


def amounts_in(text: str) -> list[float]:
    """Money-sized amounts in a reply, crore and lakh parts added together
    ("1 crore 6 lakh" -> 10_600_000)."""
    amounts: list[float] = []
    joinable = False  # the previous amount was in crore and nothing came between
    last_end = -1
    for m in _AMOUNT_RE.finditer(text):
        value = float(m.group("num").replace(",", "") + "." + (m.group("frac") or "0"))
        unit = (m.group("unit") or "").lower()
        value *= _UNITS.get(unit, 1)
        if joinable and unit in ("lakh", "lac", "লাখ", "লক্ষ") and not text[last_end:m.start()].strip():
            amounts[-1] += value
            joinable = False
        else:
            amounts.append(value)
            joinable = unit in ("crore", "কোটি")
        last_end = m.end()
    return [a for a in amounts if a >= _MIN_PRICE]


def listings_named(text: str, shown: dict[int, dict]) -> set[int]:
    """The #numbers of the shown listings a reply names, by title or price."""
    lowered = text.lower()
    amounts = amounts_in(text)
    named = set()
    for number, card in shown.items():
        title = (card.get("title") or "").strip().lower()
        if title and title in lowered:
            named.add(number)
            continue
        price = float(card.get("price") or 0)
        if price and any(abs(a - price) <= max(1.0, price * 0.005) for a in amounts):
            named.add(number)
    return named


def _form_on_screen(userdata: SessionUserdata) -> bool:
    pending = userdata.pending_booking
    return (
        pending is not None
        and pending.state != BookingState.booked
        and pending.proposed_datetime is not None
    )


def _reply_used_screen_tool(chat_ctx: llm.ChatContext) -> bool:
    """Whether this reply (everything after the customer's last message) called a
    tool that puts the shortlist or the booking form on screen."""
    for item in reversed(chat_ctx.items):
        if isinstance(item, llm.ChatMessage) and item.role == "user":
            return False
        if isinstance(item, llm.FunctionCall) and item.name in _SCREEN_TOOLS:
            return True
    return False


async def show_listing(userdata: SessionUserdata, number: int) -> bool:
    """Sends listing #number's card to the browser, unless it's already the one
    shown. False when nothing was sent."""
    card = userdata.shown_listings.get(number)
    if card is None:
        logger.info("no listing #%s to show", number)
        return False
    if userdata.focused_listing == number:
        return False
    try:
        await userdata.room.local_participant.send_text(
            json.dumps(card), topic=LISTING_FOCUS_TOPIC
        )
    except Exception:
        logger.exception("could not send listing #%s", number)
        return False
    userdata.focused_listing = number
    return True


async def focus_reply(
    stream: AsyncIterable[Any],
    userdata: SessionUserdata | None,
    chat_ctx: llm.ChatContext,
) -> AsyncIterable[Any]:
    """Passes an llm_node stream through with the markers removed, and shows
    the listing the reply is about (see the module docstring)."""
    stripper = MarkerStripper()
    spoken: list[str] = []
    # The session to show a card in; None when nothing may be shown.
    screen = userdata if (
        userdata is not None
        and not userdata.is_phone_call
        and userdata.room is not None
        and bool(userdata.shown_listings)
        and not _reply_used_screen_tool(chat_ctx)
        and not _form_on_screen(userdata)
    ) else None
    sent = False
    # A tool call in this stream that brings up the shortlist or the form.
    screen_tool = False

    async def on_markers() -> None:
        nonlocal sent
        if screen is not None and not sent and stripper.numbers:
            sent = True
            await show_listing(screen, stripper.numbers[0])

    async for chunk in stream:
        if isinstance(chunk, str):
            text = stripper.feed(chunk)
            spoken.append(text)
            await on_markers()
            if text:
                yield text
            continue
        if isinstance(chunk, llm.ChatChunk) and chunk.delta and chunk.delta.tool_calls:
            screen_tool = screen_tool or any(
                call.name in _SCREEN_TOOLS for call in chunk.delta.tool_calls
            )
        if isinstance(chunk, llm.ChatChunk) and chunk.delta and chunk.delta.content:
            text = stripper.feed(chunk.delta.content)
            spoken.append(text)
            await on_markers()
            chunk = chunk.model_copy(
                update={"delta": chunk.delta.model_copy(update={"content": text or None})}
            )
        yield chunk

    if rest := stripper.flush():
        spoken.append(rest)
        yield rest
    await on_markers()

    if screen is not None and not stripper.numbers and not screen_tool:
        named = listings_named("".join(spoken), screen.shown_listings)
        if len(named) == 1:
            await show_listing(screen, named.pop())
