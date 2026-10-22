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


def test_books_from_the_form():
    prop = _first_property()
    phone = unused_test_phone()
    ctx = _ctx()
    ctx.userdata.shown_listings[3] = prop
    out = _fill(ctx, listing_number=3, proposed_datetime=_future(), full_name="Pytest User", phone=phone)
    assert "Read back" in out
    assert ctx.userdata.pending_booking.state == BookingState.review

    summary = _book(ctx)
    assert summary.startswith(f"Booked a viewing of {prop['title']} for Pytest User at ")
    assert ctx.userdata.pending_booking.state == BookingState.booked

    db = SessionLocal()
    try:
        client = client_repo.get(db, ctx.userdata.client_id)
        assert client.phone == normalize_bd_mobile(phone)
        assert client.full_name == "Pytest User"
        assert client.email is None
    finally:
        db.close()
    (booking,) = _bookings(ctx.userdata.client_id)
    assert str(booking.property_id) == prop["id"]
    assert booking.channel == "inbound_chat"
    # No email on file: only the agency's invite, with the phone in it.
    (invite,) = _invites(booking.id)
    assert invite.recipient_type == "ceo"
    assert normalize_bd_mobile(phone) in invite.body

    # Booked once: a second yes doesn't book again.
    with pytest.raises(BookingNotReady, match="Already booked"):
        asyncio.run(book_appointment(ctx))
    assert len(_bookings(ctx.userdata.client_id)) == 1


def test_an_existing_client_is_found_by_phone_and_keeps_its_name():
    phone = unused_test_phone()
    db = SessionLocal()
    try:
        existing = client_repo.create(db, {"full_name": "Pytest Original", "phone": phone})
        _created.append(existing.id)
    finally:
        db.close()
    ctx = _ctx()
    ctx.userdata.shown_listings[1] = _first_property()
    _fill(ctx, listing_number=1, proposed_datetime=_future(), full_name="Pytest Renamed", phone=phone)
    _book(ctx)
    assert ctx.userdata.client_id == existing.id
    db = SessionLocal()
    try:
        assert client_repo.get(db, existing.id).full_name == "Pytest Original"
    finally:
        db.close()


def test_cold_call_books_for_the_lead_and_fills_its_empty_phone():
    phone = unused_test_phone()
    db = SessionLocal()
    try:
        lead = client_repo.create(db, {"full_name": "Pytest Lead", "phone": None})
        _created.append(lead.id)
        db.expunge(lead)
    finally:
        db.close()
    ctx = SimpleNamespace(
        userdata=SessionUserdata(
            channel=Channel.outbound_coldcall, room=None, client=lead, client_id=lead.id
        )
    )
    ctx.userdata.shown_listings[1] = _first_property()
    # The lead's name is on the form already.
    _fill(ctx, listing_number=1, proposed_datetime=_future(), phone=phone)
    assert ctx.userdata.pending_booking.full_name == "Pytest Lead"
    _book(ctx)

    assert ctx.userdata.client_id == lead.id
    (booking,) = _bookings(lead.id)
    assert booking.channel == "outbound_coldcall"
    db = SessionLocal()
    try:
        assert client_repo.get(db, lead.id).phone == normalize_bd_mobile(phone)
    finally:
        db.close()
    assert lead.phone == normalize_bd_mobile(phone)


def test_cold_call_keeps_the_leads_phone_on_file():
    on_file = normalize_bd_mobile(unused_test_phone())
    db = SessionLocal()
    try:
        lead = client_repo.create(db, {"full_name": "Pytest Lead", "phone": on_file})
        _created.append(lead.id)
        db.expunge(lead)
    finally:
        db.close()
    ctx = SimpleNamespace(
        userdata=SessionUserdata(channel=Channel.outbound_coldcall, room=None, client=lead)
    )
    ctx.userdata.shown_listings[1] = _first_property()
    out = _fill(ctx, listing_number=1, proposed_datetime=_future())
    # Name and phone came from the file.
    assert ctx.userdata.pending_booking.phone == on_file
    assert "Read back" in out


@pytest.mark.parametrize(
    "fields, field",
    [
        ({"proposed_datetime": "2020-01-01T10:00:00"}, "proposed_datetime"),
        ({"proposed_datetime": "next tuesday"}, "proposed_datetime"),
        ({"phone": "12345"}, "phone"),
        ({"phone": "+1 415 555 2671"}, "phone"),
        ({"full_name": "   "}, "full_name"),
        ({"listing_number": 99}, "listing_number"),
    ],
)
def test_invalid_fields_are_named(fields, field):
    ctx = _ctx()
    with pytest.raises(ToolError, match=field):
        _fill(ctx, **fields)


def test_a_time_that_passed_while_waiting_is_asked_for_again():
    ctx = _ctx()
    ctx.userdata.shown_listings[1] = _first_property()
    _fill(ctx, listing_number=1, proposed_datetime=_future(), full_name="Pytest User", phone=unused_test_phone())
    pending = ctx.userdata.pending_booking
    pending.proposed_datetime = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with pytest.raises(ToolError, match="in the past"):
        asyncio.run(book_appointment(ctx))
    assert pending.state == BookingState.collecting
    assert pending.proposed_datetime is None
    assert ctx.userdata.client_id is None


def test_dashboard_bookings_show_the_clients_name_and_phone(api):
    phone = unused_test_phone()
    ctx = _ctx()
    ctx.userdata.shown_listings[1] = _first_property()
    _fill(ctx, listing_number=1, proposed_datetime=_future(), full_name="Pytest Listed", phone=phone)
    _book(ctx)
    (booking,) = _bookings(ctx.userdata.client_id)

    listed = {row["id"]: row for row in api.get("/api/bookings").json()}
    row = listed[str(booking.id)]
    assert row["client_name"] == "Pytest Listed"
    assert row["client_phone"] == normalize_bd_mobile(phone)
    detail = api.get(f"/api/bookings/{booking.id}").json()
    assert detail["client_phone"] == normalize_bd_mobile(phone)
    assert [invite["recipient_type"] for invite in detail["invites"]] == ["ceo"]
