"""The booking form: update_booking_form, the browser form's RPC methods
(booking.submit / booking.edit / booking.confirm) and the booking-form text
stream. The room and session are fakes; bookings hit the database with test
numbers from reserved_phone and are cleaned up by the client ids created."""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from livekit.agents.llm import ToolError
from reserved_phone import delete_clients, unused_test_phone
from sqlalchemy import text

from app.agent import booking
from app.agent.booking import BOOKING_FORM_TOPIC, BookingNotReady, BookingRpc
from app.agent.tools.book_appointment import book_appointment
from app.agent.tools.booking_form import update_booking_form
from app.agent.userdata import BookingState, Channel, SessionUserdata
from app.db.session import SessionLocal

CALLER = "web-user"
_created: list = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    delete_clients(_created)
    _created.clear()


class FakeRoom:
    """Records every text stream payload by topic, and the RPC methods
    registered. `on` keeps every handler per event."""

    def __init__(self):
        self.sent: dict[str, list[dict]] = {}
        self.rpc: dict[str, object] = {}
        self.handlers: dict[str, list] = {}
        self.local_participant = self

    async def send_text(self, text, *, topic):
        self.sent.setdefault(topic, []).append(json.loads(text))

    def register_rpc_method(self, method, handler):
        self.rpc[method] = handler

    def on(self, event, handler):
        self.handlers.setdefault(event, []).append(handler)

    def forms(self) -> list[dict]:
        return self.sent.get(BOOKING_FORM_TOPIC, [])


class FakeSession:
    def __init__(self):
        self.replies: list[str] = []

    def generate_reply(self, *, instructions=None, **kwargs):
        self.replies.append(instructions)


class FakeRecorder:
    def __init__(self):
        self.rows: list[tuple] = []

    def record_tool(self, name, args, output):
        self.rows.append((name, args, output))


def _future() -> str:
    # Midday local, inside live viewing hours whenever the tests run.
    day = datetime.now(timezone.utc) + timedelta(days=3)
    return day.strftime("%Y-%m-%dT11:00:00")


def _card() -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("select id, title from properties where is_active order by price limit 1")
        ).one()
        return {"id": str(row.id), "title": row.title}
    finally:
        db.close()


def _setup(*, phone_call=False, client=None, channel=Channel.inbound_chat):
    room = FakeRoom()
    session = FakeSession()
    recorder = FakeRecorder()
    userdata = SessionUserdata(
        channel=channel, room=room, is_phone_call=phone_call, client=client
    )
    rpc = BookingRpc(
        session=session,
        userdata=userdata,
        room=room,
        linked_identity=lambda: CALLER,
        recorder=recorder,
    )
    rpc.register()
    return SimpleNamespace(
        room=room,
        session=session,
        recorder=recorder,
        userdata=userdata,
        rpc=rpc,
        ctx=SimpleNamespace(userdata=userdata),
    )


async def _rpc(t, method: str, payload: dict, caller: str = CALLER) -> dict:
    data = SimpleNamespace(
        request_id="r1", caller_identity=caller, payload=json.dumps(payload), response_timeout=15
    )
    return json.loads(await t.room.rpc[method](data))


async def _open_form(t, **fields) -> str:
    t.userdata.shown_listings[1] = _card()
    return await update_booking_form(t.ctx, listing_number=1, **fields)


def _bookings(client_id) -> int:
    db = SessionLocal()
    try:
        return db.scalar(
            text("select count(*) from bookings where client_id = :c"), {"c": client_id}
        )
    finally:
        db.close()


# ---- update_booking_form ----


def test_the_form_needs_a_time_before_review():
    async def go():
        t = _setup()
        out = await _open_form(t, full_name="Pytest Form", phone=unused_test_phone())
        pending = t.userdata.pending_booking
        assert pending.state == BookingState.collecting
        assert "which day and time" in out
        # The form isn't shown until the time is settled.
        assert t.room.forms() == []

        out = await update_booking_form(t.ctx, proposed_datetime=_future())
        assert pending.state == BookingState.review
        assert "Read back the name, phone number" in out
        states = [form["state"] for form in t.room.forms()]
        assert states == ["review"]
        assert t.room.forms()[-1]["form_id"] == pending.form_id

    asyncio.run(go())


def test_a_time_outside_viewing_hours_is_refused_politely():
    async def go():
        t = _setup()
        await _open_form(t, full_name="Pytest Form", phone=unused_test_phone())
        late = _future().replace("T11:00:00", "T19:30:00")
        with pytest.raises(ToolError) as exc:
            await update_booking_form(t.ctx, proposed_datetime=late)
        message = exc.value.message
        assert "live viewings run from 8 AM to 6 PM" in message
        assert "another date" in message
        pending = t.userdata.pending_booking
        assert pending.proposed_datetime is None
        assert pending.state == BookingState.collecting

        await update_booking_form(t.ctx, proposed_datetime=_future().replace("T11:00:00", "T17:00:00"))
        assert pending.state == BookingState.review

    asyncio.run(go())


def test_the_day_and_time_come_first_then_the_form_appears():
    async def go():
        t = _setup()
        out = await _open_form(t)
        assert "which day and time" in out
        assert "don't ask for their name or number yet" in out
        assert t.room.forms() == []

        out = await update_booking_form(t.ctx, proposed_datetime=_future())
        assert "their name, their mobile number" in out
        assert "the booking form is now on screen" in out
        assert "Never ask for an email address" in out
        assert [form["state"] for form in t.room.forms()] == ["collecting"]

    asyncio.run(go())


def test_pushed_state_shows_the_local_phone_and_listing():
    async def go():
        t = _setup()
        await _open_form(t, proposed_datetime=_future(), full_name="  Pytest   Form ", phone="+৮৮০ ১৩৯৯-৯৯৯০০০")
        form = t.room.forms()[-1]
        assert form["phone"] == "01399999000"
        assert form["full_name"] == "Pytest Form"
        assert form["property_title"] == t.userdata.shown_listings[1]["title"]
        assert form["state"] == "review"
        assert form["errors"] == {}

    asyncio.run(go())


def test_an_invalid_field_is_named_and_the_rest_kept():
    async def go():
        t = _setup()
        with pytest.raises(ToolError, match="phone"):
            await _open_form(
                t, proposed_datetime=_future(), full_name="Pytest Form", phone="12345"
            )
        pending = t.userdata.pending_booking
        assert pending.full_name == "Pytest Form"
        assert pending.phone is None
        assert t.room.forms()[-1]["errors"] == {"phone": booking.PHONE_ERROR}

    asyncio.run(go())


def test_this_one_on_a_property_page_fills_the_property():
    async def go():
        t = _setup()
        card = _card()
        t.userdata.shown_listings[4] = card
        t.userdata.viewing_property_id = uuid.UUID(card["id"])
        await update_booking_form(t.ctx, proposed_datetime=_future())
        assert t.userdata.pending_booking.property_title == card["title"]

    asyncio.run(go())


def test_cold_call_prefills_name_and_phone_from_the_lead():
    async def go():
        lead = SimpleNamespace(id=uuid.uuid4(), full_name="Pytest Lead", phone="01711-234567", email=None)
        t = _setup(client=lead, channel=Channel.outbound_coldcall)
        await _open_form(t, proposed_datetime=_future())
        pending = t.userdata.pending_booking
        assert pending.full_name == "Pytest Lead"
        assert pending.phone == "+8801711234567"
        assert pending.state == BookingState.review

    asyncio.run(go())


# ---- RPC ----


def test_submit_from_the_wrong_caller_is_refused():
    async def go():
        t = _setup()
        await _open_form(t)
        form_id = t.userdata.pending_booking.form_id
        reply = await _rpc(t, booking.RPC_SUBMIT, {"form_id": form_id, "full_name": "X", "phone": unused_test_phone()}, caller="someone-else")
        assert reply["ok"] is False
        assert t.userdata.pending_booking.full_name is None

    asyncio.run(go())


@pytest.mark.parametrize("method", [booking.RPC_SUBMIT, booking.RPC_EDIT, booking.RPC_CONFIRM])
def test_a_stale_form_id_is_refused(method):
    async def go():
        t = _setup()
        await _open_form(t)
        reply = await _rpc(t, method, {"form_id": "old", "full_name": "X", "phone": "01711234567"})
        assert reply == {"ok": False, "errors": {"form": "This form is out of date."}}
        assert t.session.replies == []

    asyncio.run(go())


def test_submit_with_bad_values_returns_field_errors():
    async def go():
        t = _setup()
        await _open_form(t, proposed_datetime=_future())
        form_id = t.userdata.pending_booking.form_id
        reply = await _rpc(t, booking.RPC_SUBMIT, {"form_id": form_id, "full_name": " ", "phone": "0171"})
        assert reply["ok"] is False
        assert set(reply["errors"]) == {"full_name", "phone"}
        assert t.userdata.pending_booking.state == BookingState.collecting
        assert t.room.forms()[-1]["errors"] == reply["errors"]
        assert t.session.replies == []

    asyncio.run(go())


def test_submit_completes_the_form_and_asks_for_the_read_back():
    async def go():
        t = _setup()
        await _open_form(t, proposed_datetime=_future())
        form_id = t.userdata.pending_booking.form_id
        reply = await _rpc(t, booking.RPC_SUBMIT, {"form_id": form_id, "full_name": "Pytest Form", "phone": "01711234567"})
        assert reply == {"ok": True, "errors": {}}
        assert t.userdata.pending_booking.state == BookingState.review
        assert t.room.forms()[-1]["state"] == "review"
        (instructions,) = t.session.replies
        assert "Read back the name, phone number" in instructions
        assert "01711234567" in instructions

    asyncio.run(go())


def test_submit_without_a_time_asks_for_it():
    async def go():
        t = _setup()
        await _open_form(t)
        form_id = t.userdata.pending_booking.form_id
        reply = await _rpc(t, booking.RPC_SUBMIT, {"form_id": form_id, "full_name": "Pytest Form", "phone": "01711234567"})
        assert reply["ok"] is True
        assert t.userdata.pending_booking.state == BookingState.collecting
        (instructions,) = t.session.replies
        assert "the date and time" in instructions

    asyncio.run(go())


def test_edit_after_review_stops_a_spoken_yes_from_booking():
    async def go():
        t = _setup()
        await _open_form(t, proposed_datetime=_future(), full_name="Pytest Form", phone=unused_test_phone())
        pending = t.userdata.pending_booking
        assert pending.state == BookingState.review
        reply = await _rpc(t, booking.RPC_EDIT, {"form_id": pending.form_id})
        assert reply["ok"] is True
        assert pending.state == BookingState.collecting
        assert t.room.forms()[-1]["state"] == "collecting"
        with pytest.raises(BookingNotReady, match="changing the details"):
            await book_appointment(t.ctx)
        reply = await _rpc(t, booking.RPC_CONFIRM, {"form_id": pending.form_id})
        assert reply["ok"] is False
        assert t.userdata.client_id is None

    asyncio.run(go())


def test_confirm_books_records_the_tool_row_and_tells_the_customer():
    async def go():
        t = _setup()
        await _open_form(t, proposed_datetime=_future(), full_name="Pytest Form", phone=unused_test_phone())
        pending = t.userdata.pending_booking
        reply = await _rpc(t, booking.RPC_CONFIRM, {"form_id": pending.form_id})
        assert reply == {"ok": True, "errors": {}}
        await t.rpc.settle()
        _created.append(t.userdata.client_id)

        assert pending.state == BookingState.booked
        assert _bookings(t.userdata.client_id) == 1
        ((name, args, output),) = t.recorder.rows
        assert (name, args) == ("book_appointment", {})
        assert output.startswith("Booked a viewing")
        assert t.room.forms()[-1]["state"] == "booked"
        assert "Booked a viewing" in t.session.replies[-1]

    asyncio.run(go())


@pytest.mark.parametrize("click_first", [True, False])
def test_a_confirm_click_and_a_spoken_yes_book_once(click_first):
    async def go():
        t = _setup()
        await _open_form(t, proposed_datetime=_future(), full_name="Pytest Form", phone=unused_test_phone())
        form_id = t.userdata.pending_booking.form_id
        if click_first:
            click = await _rpc(t, booking.RPC_CONFIRM, {"form_id": form_id})
            spoken = await asyncio.gather(book_appointment(t.ctx), return_exceptions=True)
        else:
            spoken = await asyncio.gather(
                book_appointment(t.ctx),
                _rpc(t, booking.RPC_CONFIRM, {"form_id": form_id}),
                return_exceptions=True,
            )
            click = spoken.pop()
        await t.rpc.settle()
        _created.append(t.userdata.client_id)

        assert t.userdata.pending_booking.state == BookingState.booked
        assert _bookings(t.userdata.client_id) == 1
        if click_first:
            assert click["ok"] is True
            assert isinstance(spoken[0], BookingNotReady)
        else:
            assert isinstance(spoken[0], str) and spoken[0].startswith("Booked")
            assert click["ok"] is False

    asyncio.run(go())


def test_phone_calls_get_no_form_stream():
    async def go():
        t = _setup(phone_call=True)
        out = await _open_form(t, proposed_datetime=_future(), full_name="Pytest Form", phone=unused_test_phone())
        assert "press Confirm" not in out
        await book_appointment(t.ctx)
        _created.append(t.userdata.client_id)
        assert t.room.sent == {}

    asyncio.run(go())


def test_a_new_form_after_booking_keeps_name_and_phone():
    async def go():
        t = _setup()
        phone = unused_test_phone()
        await _open_form(t, proposed_datetime=_future(), full_name="Pytest Form", phone=phone)
        await book_appointment(t.ctx)
        _created.append(t.userdata.client_id)
        first = t.userdata.pending_booking
        await update_booking_form(t.ctx, listing_number=1)
        second = t.userdata.pending_booking
        assert second.form_id != first.form_id
        assert (second.full_name, second.phone) == (first.full_name, first.phone)
        assert second.proposed_datetime is None

    asyncio.run(go())
