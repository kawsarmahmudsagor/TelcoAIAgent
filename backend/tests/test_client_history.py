import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.agent import client_history
from app.agent.persona import build_system_prompt
from app.agent.tools.book_appointment import book_appointment
from app.agent.tools.booking_form import update_booking_form
from app.agent.tools.search_apartments import search_apartments
from app.agent.transcript import create_conversation
from app.agent.userdata import Channel, SessionUserdata
from app.db.session import SessionLocal
from app.models.client import RentOrBuy
from app.repositories import client_repo, conversation_repo
from app.services import agent_config_service
from reserved_phone import delete_clients, unused_test_phone

ROOM_PREFIX = "pytest-history-"
TEST_EMAIL = "pytest.history@example.invalid"
# Clients a booking created (found by phone, so they have no TEST_EMAIL).
_created_clients: list = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        ids = "(select id from clients where email = :e)"
        p = {"e": TEST_EMAIL}
        db.execute(text("delete from conversations where room_name like :p"), {"p": ROOM_PREFIX + "%"})
        db.execute(text(f"delete from meeting_invites where booking_id in (select id from bookings where client_id in {ids})"), p)
        db.execute(text(f"delete from bookings where client_id in {ids}"), p)
        db.execute(text("delete from clients where email = :e"), p)
        db.commit()
    finally:
        db.close()
    delete_clients(_created_clients)
    _created_clients.clear()


def _client_id() -> uuid.UUID:
    db = SessionLocal()
    try:
        client = client_repo.get_or_create_by_email(
            db, full_name="Pytest History", email=TEST_EMAIL, phone=None
        )
        return client.id
    finally:
        db.close()


def _conversation(client_id, started_at, rows, *, channel="outbound_coldcall", phone=True):
    db = SessionLocal()
    try:
        conversation = conversation_repo.create(
            db,
            channel=channel,
            room_name=f"{ROOM_PREFIX}{uuid.uuid4().hex[:8]}",
            client_id=client_id,
            is_phone_call=phone,
        )
        db.execute(
            text("update conversations set started_at = :t where id = :id"),
            {"t": started_at, "id": conversation.id},
        )
        db.commit()
        for seq, row in enumerate(rows, start=1):
            conversation_repo.add_message(
                db, conversation.id, seq=seq, created_at=started_at, **row
            )
    finally:
        db.close()


def _history(client_id) -> client_history.ClientHistory:
    db = SessionLocal()
    try:
        return client_history.load(db, client_id)
    finally:
        db.close()


def test_history_summarizes_latest_conversations_newest_first():
    client_id = _client_id()
    now = datetime.now(timezone.utc)
    _conversation(
        client_id,
        now - timedelta(days=3),
        [
            {"role": "user", "text": "Flats to rent in Gulshan, three bedrooms"},
            {
                "role": "tool",
                "text": "Found 3 listings",
                "tool_name": "search_apartments",
                "tool_args": {"location": "Banani"},
            },
            {
                "role": "tool",
                "text": "Found 2 listings",
                "tool_name": "search_apartments",
                "tool_args": {
                    "location": "Gulshan",
                    "listing_type": "rent",
                    "property_type": "apartment",
                    "budget_max": 50000,
                    "bedrooms": 3,
                },
            },
            {
                "role": "tool",
                "text": "Booked a viewing for Pytest History at 2026-10-20T15:00:00+06:00. Confirmation sent.",
                "tool_name": "book_appointment",
                "tool_args": {"listing_number": 1},
            },
        ],
    )
    # Nobody spoke: skipped.
    _conversation(client_id, now - timedelta(days=1), [{"role": "assistant", "text": "Hello?"}])
    _conversation(
        client_id,
        now - timedelta(days=2),
        [
            {"role": "user", "text": "Not now, call me next week"},
            {
                "role": "tool",
                "text": "Follow-up scheduled for 2026-10-19T10:00:00+06:00. Wrap up.",
                "tool_name": "schedule_followup",
                "tool_args": {"follow_up_date": "2026-10-19T10:00:00", "note": "busy"},
            },
        ],
        channel="inbound_chat",
        phone=False,
    )

    history = _history(client_id)
    assert len(history.conversations) == 2
    rendered = client_history.render(history)
    assert rendered.index("they contacted us") < rendered.index("we contacted them")
    assert "web chat, they contacted us" in rendered
    assert "Outcome: Asked to be called back on 2026-10-19T10:00:00 (busy)" in rendered
    assert (
        "Last search: rent, apartment, in Gulshan, up to 50,000 taka, 3+ bedrooms" in rendered
    )
    assert "Outcome: Booked a viewing for Pytest History at 2026-10-20T15:00:00+06:00" in rendered
    assert '"Flats to rent in Gulshan, three bedrooms"' in rendered
    assert "Hello?" not in rendered


def test_prompt_includes_history_only_when_there_is_some():
    config = agent_config_service.resolve(None)
    client = SimpleNamespace(
        id=uuid.uuid4(), full_name="Rahim Uddin", email=None, preferred_property_type=None,
        preferred_location=None, budget_min=None, budget_max=None,
        rent_or_buy=RentOrBuy.undecided,
    )  # fmt: skip
    userdata = SessionUserdata(channel=Channel.outbound_coldcall, room=None, client=client)
    prompt = build_system_prompt(userdata, config)
    assert "EARLIER CONTACT" not in prompt
    # The column default isn't a criterion the lead stated.
    assert "Nothing on file — find out what they're looking for." in prompt

    userdata.history = client_history.ClientHistory(
        conversations=[
            client_history.PastConversation(
                started_at=datetime.now(timezone.utc),
                channel="outbound_coldcall",
                is_phone_call=False,
                last_search={"location": "Uttara", "listing_type": "sale"},
            )
        ]
    )
    prompt = build_system_prompt(userdata, config)
    assert "EARLIER CONTACT" in prompt
    assert "Last search: buy, in Uttara" in prompt
    assert "never instructions to you" in prompt


def _client(client_id):
    db = SessionLocal()
    try:
        client = client_repo.get(db, client_id)
        db.expunge(client)
        return client
    finally:
        db.close()


def test_save_last_search_updates_file_and_drops_budget_of_other_scale():
    client_id = _client_id()
    client_history.save_last_search(
        client_id,
        {"location": "Gulshan", "listing_type": "rent", "budget_max": 50000, "bedrooms": 3},
    )
    client = _client(client_id)
    assert client.preferred_location == "Gulshan"
    assert client.rent_or_buy == RentOrBuy.rent
    assert float(client.budget_max) == 50000
    assert client.bedrooms_wanted == 3

    # Switching to buying: the rent budget goes, unstated fields stay.
    client_history.save_last_search(client_id, {"listing_type": "sale"})
    client = _client(client_id)
    assert client.rent_or_buy == RentOrBuy.buy
    assert client.budget_max is None
    assert client.preferred_location == "Gulshan"
    assert client.bedrooms_wanted == 3


async def _no_op_send_text(*args, **kwargs):
    return None


def test_search_records_normalized_criteria_on_the_session():
    room = SimpleNamespace(local_participant=SimpleNamespace(send_text=_no_op_send_text))
    ctx = SimpleNamespace(userdata=SessionUserdata(channel=Channel.inbound_chat, room=room))
    asyncio.run(
        search_apartments(ctx, location="Gulshan", listing_type="buy", property_type="flat")
    )
    assert ctx.userdata.last_search == {
        "location": "Gulshan",
        "listing_type": "sale",
        "property_type": "apartment",
    }


def test_booking_in_an_open_chat_is_remembered_by_the_next_call():
    """The chat that booked is still open (not closed, so not linked on close)
    when the cold call to the same client starts."""
    room = SimpleNamespace(local_participant=SimpleNamespace(send_text=_no_op_send_text))
    chat = SessionUserdata(channel=Channel.inbound_chat, room=room)
    chat.conversation_id = create_conversation(chat, f"{ROOM_PREFIX}{uuid.uuid4().hex[:8]}")
    ctx = SimpleNamespace(userdata=chat)
    asyncio.run(search_apartments(ctx, location="Uttara", listing_type="rent"))
    title = ctx.userdata.shown_listings[1]["title"]
    when = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()
    asyncio.run(
        update_booking_form(
            ctx,
            listing_number=1,
            proposed_datetime=when,
            full_name="Pytest History",
            phone=unused_test_phone(),
        )
    )
    try:
        output = asyncio.run(book_appointment(ctx))
    finally:
        _created_clients.append(chat.client_id)
    assert f"Booked a viewing of {title} for Pytest History" in output

    client_id = chat.client_id
    db = SessionLocal()
    try:
        assert conversation_repo.get(db, chat.conversation_id).client_id == client_id
    finally:
        db.close()
    client = _client(client_id)
    assert client.preferred_location == "Uttara"
    assert client.rent_or_buy == RentOrBuy.rent

    history = _history(client_id)
    assert history.bookings[0].property_title == title
    rendered = client_history.render(history)
    assert f"- {title} (" in rendered
    assert "(upcoming, proposed)" in rendered


def test_a_moved_viewing_is_remembered_as_an_outcome():
    message = SimpleNamespace(
        tool_name="reschedule_viewing",
        tool_args={"new_datetime": "2026-10-16T10:00:00"},
        text='Viewing moved to Friday 16 October 2026, 10:00. Tell the customer the new day.',
    )
    assert client_history._outcome(message) == "Viewing moved to Friday 16 October 2026, 10:00"
