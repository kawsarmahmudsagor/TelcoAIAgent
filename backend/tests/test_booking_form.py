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
















# ---- RPC ----
