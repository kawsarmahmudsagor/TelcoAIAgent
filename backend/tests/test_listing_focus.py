"""The [show:N] marker and its fallback (app.agent.listing_focus)."""

import asyncio
import json

from livekit.agents import llm

from app.agent import listing_focus
from app.agent.listing_focus import LISTING_FOCUS_TOPIC, MarkerStripper, amounts_in, focus_reply
from app.agent.userdata import BookingState, Channel, PendingBooking, SessionUserdata


class Room:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []
        self.local_participant = self

    async def send_text(self, text, *, topic):
        self.sent.append((topic, json.loads(text)))


def _card(id_, title, price, listing_type="rent"):
    return {"id": id_, "title": title, "price": price, "listing_type": listing_type}


SHOWN = {
    1: _card("a", "Modern 2BR Apartment in Uttara Sector 7", 18_000),
    2: _card("b", "Cozy 2BR Apartment in Uttara Sector 4", 22_000),
    3: _card("c", "Lakeview 3BR Apartment in Gulshan 2", 4_000_000, "sale"),
}


def _userdata(**kwargs) -> SessionUserdata:
    data = SessionUserdata(channel=Channel.inbound_chat, room=Room(), **kwargs)
    data.shown_listings = dict(SHOWN)
    return data


def _ctx(*items) -> llm.ChatContext:
    ctx = llm.ChatContext()
    ctx.items.append(llm.ChatMessage(role="user", content=["the second one"]))
    ctx.items.extend(items)
    return ctx


def _run(chunks, userdata, ctx=None):
    async def stream():
        for chunk in chunks:
            yield chunk

    async def go():
        out = []
        async for chunk in focus_reply(stream(), userdata, ctx or _ctx()):
            if isinstance(chunk, str):
                out.append(chunk)
            elif chunk.delta and chunk.delta.content:
                out.append(chunk.delta.content)
        return "".join(out)

    return asyncio.run(go())


def _chunk(text):
    return llm.ChatChunk(id="x", delta=llm.ChoiceDelta(role="assistant", content=text))


def _sent(userdata):
    return userdata.room.sent


# ---- the marker ----


def test_the_marker_is_stripped_and_its_card_sent():
    data = _userdata()
    text = _run(["[show:2] এই ফ্ল্যাটটি উত্তরায়।"], data)
    assert text == "এই ফ্ল্যাটটি উত্তরায়।"
    assert _sent(data) == [(LISTING_FOCUS_TOPIC, SHOWN[2])]
    assert data.focused_listing == 2


def test_a_marker_split_across_chunks_is_stripped():
    data = _userdata()
    text = _run([_chunk("[sh"), _chunk("ow: #"), _chunk("3]"), _chunk(" Gulshan flat.")], data)
    assert text == "Gulshan flat."
    assert _sent(data) == [(LISTING_FOCUS_TOPIC, SHOWN[3])]


def test_bangla_digits_in_the_marker():
    data = _userdata()
    assert _run(["[show:১] ঠিক আছে।"], data) == "ঠিক আছে।"
    assert data.focused_listing == 1


def test_other_brackets_pass_through():
    stripper = MarkerStripper()
    out = stripper.feed("Price [") + stripper.feed("approx] 18,000") + stripper.flush()
    assert out == "Price [approx] 18,000"
    assert stripper.numbers == []


def test_an_unknown_listing_number_sends_nothing():
    data = _userdata()
    assert _run(["[show:9] Hi."], data) == "Hi."
    assert _sent(data) == []


def test_the_card_already_on_screen_is_not_sent_again():
    data = _userdata()
    data.focused_listing = 2
    _run(["[show:2] Again."], data)
    assert _sent(data) == []


def test_a_phone_call_strips_the_marker_but_sends_nothing():
    data = _userdata(is_phone_call=True)
    assert _run(["[show:2] Hello."], data) == "Hello."
    assert _sent(data) == []


def test_nothing_is_sent_while_the_booking_form_is_on_screen():
    data = _userdata()
    data.pending_booking = PendingBooking(
        form_id="f", state=BookingState.collecting, proposed_datetime="2026-10-20T15:00:00+06:00"
    )
    _run(["[show:2] Your viewing."], data)
    assert _sent(data) == []


def test_nothing_is_sent_in_a_reply_that_searched():
    data = _userdata()
    ctx = _ctx(llm.FunctionCall(call_id="c", name="search_apartments", arguments="{}"))
    _run(["[show:2] Found some."], data, ctx)
    assert _sent(data) == []


def test_no_session_still_strips():
    assert _run(["[show:2] Hi."], None) == "Hi."


# ---- the fallback ----


def test_a_reply_naming_one_price_shows_that_listing():
    data = _userdata()
    _run(["২২,০০০ টাকার ফ্ল্যাটটিতে ২টি বেডরুম আছে।"], data)
    assert _sent(data) == [(LISTING_FOCUS_TOPIC, SHOWN[2])]


def test_a_reply_naming_one_title_shows_that_listing():
    data = _userdata()
    _run(["The Lakeview 3BR Apartment in Gulshan 2 has a lake view."], data)
    assert _sent(data) == [(LISTING_FOCUS_TOPIC, SHOWN[3])]


def test_a_reply_naming_two_listings_shows_nothing():
    data = _userdata()
    _run(["One is 18,000 taka, the other 22,000 taka."], data)
    assert _sent(data) == []


def test_a_reply_that_calls_the_booking_form_shows_nothing():
    data = _userdata()
    call = llm.FunctionToolCall(name="update_booking_form", arguments="{}", call_id="c")
    _run(
        [
            _chunk("Okay, the 22,000 taka flat."),
            llm.ChatChunk(id="x", delta=llm.ChoiceDelta(role="assistant", tool_calls=[call])),
        ],
        data,
    )
    assert _sent(data) == []


def test_amounts_in_lakh_and_crore():
    assert amounts_in("৪০ লাখ টাকা") == [4_000_000]
    assert amounts_in("1 crore 6 lakh taka") == [10_600_000]
    assert amounts_in("১.২ কোটি") == [12_000_000]
    assert amounts_in("১৪ হাজার") == [14_000]
    # Bedrooms and sizes aren't prices.
    assert amounts_in("2 bedrooms, 900 sqft") == []


def test_the_fallback_matches_a_sale_price_in_lakh():
    data = _userdata()
    _run(["গুলশানের ফ্ল্যাটটির দাম ৪০ লাখ টাকা।"], data)
    assert listing_focus.listings_named("৪০ লাখ টাকা", SHOWN) == {3}
    assert _sent(data) == [(LISTING_FOCUS_TOPIC, SHOWN[3])]
