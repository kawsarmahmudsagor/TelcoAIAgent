"""book_appointment books the form (userdata.pending_booking), only once it has
been read back (state review). Bookings find or create the client by phone,
with test numbers from reserved_phone; cleanup is by the client ids created."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from livekit.agents.llm import ToolError
from reserved_phone import delete_clients, unused_test_phone
from sqlalchemy import text

from app.agent.booking import BookingNotReady
from app.agent.tools.book_appointment import book_appointment
from app.agent.tools.booking_form import update_booking_form
from app.agent.userdata import BookingState, Channel, SessionUserdata
from app.db.session import SessionLocal
from app.repositories import client_repo
from app.services.phone_numbers import normalize_bd_mobile

_created: list = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    delete_clients(_created)
    _created.clear()


def _ctx(**userdata) -> SimpleNamespace:
    return SimpleNamespace(
        userdata=SessionUserdata(channel=Channel.inbound_chat, room=None, **userdata)
    )


def _future() -> str:
    # Midday local, inside live viewing hours whenever the tests run.
    day = datetime.now(timezone.utc) + timedelta(days=3)
    return day.strftime("%Y-%m-%dT11:00:00")


def _first_property() -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("select id, title from properties where is_active order by price limit 1")
        ).one()
        return {"id": str(row.id), "title": row.title}
    finally:
        db.close()


def _fill(ctx, **fields) -> str:
    return asyncio.run(update_booking_form(ctx, **fields))


def _book(ctx) -> str:
    try:
        return asyncio.run(book_appointment(ctx))
    finally:
        _created.append(ctx.userdata.client_id)


def _bookings(client_id) -> list:
    db = SessionLocal()
    try:
        return list(
            db.execute(
                text(
                    "select b.id, b.property_id, b.channel from bookings b "
                    "where b.client_id = :c"
                ),
                {"c": client_id},
            )
        )
    finally:
        db.close()


def _invites(booking_id) -> list:
    db = SessionLocal()
    try:
        return list(
            db.execute(
                text("select recipient_type, body from meeting_invites where booking_id = :b"),
                {"b": booking_id},
            )
        )
    finally:
        db.close()


def test_refuses_without_a_form():
    with pytest.raises(BookingNotReady, match="no booking form"):
        asyncio.run(book_appointment(_ctx()))


def test_refuses_until_the_form_is_complete():
    ctx = _ctx()
    _fill(ctx, full_name="Pytest User", phone=unused_test_phone())
    assert ctx.userdata.pending_booking.state == BookingState.collecting
    with pytest.raises(BookingNotReady, match="the date and time"):
        asyncio.run(book_appointment(ctx))
    assert ctx.userdata.client_id is None










@pytest.mark.parametrize(
    "fields, field",
    [
        ({"proposed_datetime": "2020-01-01T10:00:00"}, "proposed_datetime"),
        ({"proposed_datetime": "next tuesday"}, "proposed_datetime"),
        ({"phone": "12345"}, "phone"),
        ({"phone": "+1 415 555 2671"}, "phone"),
        ({"full_name": "   "}, "full_name"),
    ],
)
def test_invalid_fields_are_named(fields, field):
    ctx = _ctx()
    with pytest.raises(ToolError, match=field):
        _fill(ctx, **fields)
