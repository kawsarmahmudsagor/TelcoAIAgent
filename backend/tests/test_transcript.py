import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from livekit.agents.llm import AgentHandoff, ChatMessage, FunctionCall, FunctionCallOutput
from livekit.agents.voice.events import ConversationItemAddedEvent, FunctionToolsExecutedEvent
from sqlalchemy import text

from app.agent import transcript
from app.agent.transcript import TOOL_OUTPUT_MAX_CHARS, TranscriptRecorder
from app.agent.userdata import Channel, SessionUserdata
from app.db.session import SessionLocal
from app.models.conversation import Conversation
from app.repositories import client_repo, conversation_repo
from app.scheduler import jobs

ROOM_PREFIX = "pytest-transcript-"
TEST_EMAIL = "pytest.transcript@example.invalid"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        db.execute(text("delete from conversations where room_name like :p"), {"p": ROOM_PREFIX + "%"})
        db.execute(text("delete from clients where email = :e"), {"e": TEST_EMAIL})
        db.commit()
    finally:
        db.close()


class _FakeSession:
    """Records handlers like AgentSession.on, and fires events at them."""

    def __init__(self):
        self.handlers: dict[str, list] = {}

    def on(self, event: str, callback) -> None:
        assert not asyncio.iscoroutinefunction(callback), "session.on rejects async callbacks"
        self.handlers.setdefault(event, []).append(callback)

    def emit(self, event: str, payload) -> None:
        for callback in self.handlers.get(event, []):
            callback(payload)


def _userdata(**kwargs) -> SessionUserdata:
    return SessionUserdata(channel=Channel.inbound_chat, room=None, **kwargs)


def _room() -> str:
    return f"{ROOM_PREFIX}{uuid.uuid4().hex[:8]}"


def _message(role: str, text: str) -> ConversationItemAddedEvent:
    return ConversationItemAddedEvent(item=ChatMessage(role=role, content=[text]))


def _tools_event(*calls: tuple[str, str, str]) -> FunctionToolsExecutedEvent:
    function_calls, outputs = [], []
    for index, (name, arguments, output) in enumerate(calls):
        call_id = f"call_{index}"
        function_calls.append(FunctionCall(call_id=call_id, name=name, arguments=arguments))
        outputs.append(
            FunctionCallOutput(call_id=call_id, name=name, output=output, is_error=False)
        )
    return FunctionToolsExecutedEvent(function_calls=function_calls, function_call_outputs=outputs)


def _rows(conversation_id: uuid.UUID):
    db = SessionLocal()
    try:
        return [
            (m.seq, m.role, m.text, m.tool_name, m.tool_args)
            for m in conversation_repo.list_messages(db, conversation_id)
        ]
    finally:
        db.close()


def _conversation(conversation_id: uuid.UUID) -> Conversation:
    db = SessionLocal()
    try:
        conversation = conversation_repo.get(db, conversation_id)
        db.expunge(conversation)
        return conversation
    finally:
        db.close()


def test_recorder_stores_messages_and_tools_in_order():
    async def run():
        session = _FakeSession()
        recorder = await TranscriptRecorder.start(session, _userdata(), _room())
        session.emit("conversation_item_added", _message("assistant", "Hi, I'm Alexa."))
        session.emit("conversation_item_added", _message("user", "Flats in Gulshan?"))
        session.emit(
            "function_tools_executed",
            _tools_event(
                ("search_apartments", '{"location": "Gulshan"}', "Found 3 listings"),
                ("book_appointment", "not json", "x" * 2000),
            ),
        )
        session.emit("conversation_item_added", _message("assistant", "Here are three."))
        await recorder.close()
        return recorder.conversation_id

    conversation_id = asyncio.run(run())
    rows = _rows(conversation_id)
    assert [r[0] for r in rows] == [1, 2, 3, 4, 5]
    assert [r[1] for r in rows] == ["assistant", "user", "tool", "tool", "assistant"]
    assert rows[1][2] == "Flats in Gulshan?"
    assert rows[2][3:] == ("search_apartments", {"location": "Gulshan"})
    assert rows[2][2] == "Found 3 listings"
    assert rows[3][4] == {"raw": "not json"}
    assert len(rows[3][2]) == TOOL_OUTPUT_MAX_CHARS

    conversation = _conversation(conversation_id)
    assert conversation.status == "ended"
    assert conversation.ended_at is not None
    assert conversation.message_count == 5
    assert conversation.channel == "inbound_chat"


@pytest.mark.parametrize("rows_first", [True, False])
def test_rows_after_a_user_message_follow_it_in_order(rows_first):
    """A filler line and the prefetched lookups land right after their user
    message, filler first, whether they reach the recorder before the message
    (said inside the turn hook) or after it (another handler of the same event)."""

    async def run():
        session = _FakeSession()
        recorder = await TranscriptRecorder.start(session, _userdata(), _room())
        user = _message("user", "Flats in Gulshan?")
        message_id = user.item.id
        if rows_first:
            recorder.record_tool_after(message_id, "search_apartments", {"location": "Gulshan"}, "Found 3")
            recorder.record_assistant_after(message_id, "Let me find those for you.")
            session.emit("conversation_item_added", user)
        else:
            recorder.record_assistant_after(message_id, "Let me find those for you.")
            session.emit("conversation_item_added", user)
            recorder.record_tool_after(message_id, "search_apartments", {"location": "Gulshan"}, "Found 3")
        session.emit("conversation_item_added", _message("assistant", "Here are three."))
        await recorder.close()
        return recorder.conversation_id

    rows = _rows(asyncio.run(run()))
    assert [(r[1], r[2]) for r in rows] == [
        ("user", "Flats in Gulshan?"),
        ("assistant", "Let me find those for you."),
        ("tool", "Found 3"),
        ("assistant", "Here are three."),
    ]


def test_rows_of_a_dropped_turn_are_never_stored():
    async def run():
        session = _FakeSession()
        recorder = await TranscriptRecorder.start(session, _userdata(), _room())
        recorder.record_assistant_after("never-added", "One moment.")
        session.emit("conversation_item_added", _message("user", "Hello"))
        await recorder.close()
        return recorder.conversation_id

    rows = _rows(asyncio.run(run()))
    assert [(r[1], r[2]) for r in rows] == [("user", "Hello")]


def test_record_tool_stores_a_booking_made_outside_the_llm():
    """A Confirm click on the booking form books without a tool call; the row
    record_tool writes is what client_history reads the booking from."""

    async def run():
        session = _FakeSession()
        recorder = await TranscriptRecorder.start(session, _userdata(), _room())
        session.emit("conversation_item_added", _message("user", "Book it"))
        recorder.record_tool("book_appointment", {}, "Booked a viewing of X for Y at Z. More.")
        await recorder.close()
        return recorder.conversation_id

    rows = _rows(asyncio.run(run()))
    assert rows[1] == (2, "tool", "Booked a viewing of X for Y at Z. More.", "book_appointment", {})


def test_empty_system_and_handoff_items_are_skipped():
    async def run():
        session = _FakeSession()
        recorder = await TranscriptRecorder.start(session, _userdata(), _room())
        session.emit("conversation_item_added", _message("system", "You are..."))
        session.emit("conversation_item_added", _message("developer", "Be brief"))
        session.emit("conversation_item_added", _message("user", "   "))
        session.emit(
            "conversation_item_added", ConversationItemAddedEvent(item=AgentHandoff(new_agent_id="a"))
        )
        session.emit("conversation_item_added", _message("user", "hello"))
        await recorder.close()
        return recorder.conversation_id

    conversation_id = asyncio.run(run())
    assert [(r[0], r[1], r[2]) for r in _rows(conversation_id)] == [(1, "user", "hello")]


def test_close_drains_queue_before_ending(monkeypatch):
    real_insert = transcript._insert
    order: list[str] = []

    def _slow_insert(conversation_id, row):
        time.sleep(0.05)
        real_insert(conversation_id, row)
        order.append(f"insert {row['seq']}")

    real_finish = transcript._finish

    def _finish(conversation_id, client_id):
        order.append("finish")
        real_finish(conversation_id, client_id)

    monkeypatch.setattr(transcript, "_insert", _slow_insert)
    monkeypatch.setattr(transcript, "_finish", _finish)

    async def run():
        session = _FakeSession()
        recorder = await TranscriptRecorder.start(session, _userdata(), _room())
        for index in range(4):
            session.emit("conversation_item_added", _message("user", f"message {index}"))
        await recorder.close()
        # Late items after close are dropped, not written after "ended".
        session.emit("conversation_item_added", _message("user", "too late"))
        await recorder.close()  # idempotent
        return recorder.conversation_id

    conversation_id = asyncio.run(run())
    assert order == ["insert 1", "insert 2", "insert 3", "insert 4", "finish"]
    assert len(_rows(conversation_id)) == 4
    assert _conversation(conversation_id).status == "ended"


def test_close_links_conversation_to_lead_found_during_session():
    db = SessionLocal()
    try:
        client = client_repo.get_or_create_by_email(
            db, full_name="Pytest Transcript", email=TEST_EMAIL, phone=None
        )
        client_id = client.id
    finally:
        db.close()

    async def run():
        userdata = _userdata()
        recorder = await TranscriptRecorder.start(_FakeSession(), userdata, _room())
        assert _conversation(recorder.conversation_id).client_id is None
        userdata.client_id = client_id  # what book_appointment does
        await recorder.close()
        return recorder.conversation_id

    assert _conversation(asyncio.run(run())).client_id == client_id


def test_start_records_cold_call_metadata():
    userdata = SessionUserdata(
        channel=Channel.outbound_coldcall,
        room=None,
        client=SimpleNamespace(id=None),
        is_phone_call=True,
    )

    async def run():
        recorder = await TranscriptRecorder.start(_FakeSession(), userdata, _room())
        await recorder.close()
        return recorder.conversation_id

    conversation = _conversation(asyncio.run(run()))
    assert conversation.channel == "outbound_coldcall"
    assert conversation.is_phone_call is True


def test_stale_sweep_ends_only_idle_active_conversations():
    db = SessionLocal()
    try:
        stale = conversation_repo.create(db, channel="inbound_chat", room_name=_room())
        fresh = conversation_repo.create(db, channel="inbound_chat", room_name=_room())
        idle_since = datetime.now(timezone.utc) - jobs.STALE_CONVERSATION_IDLE - timedelta(minutes=5)
        db.execute(
            text("update conversations set updated_at = :t, started_at = :t where id = :id"),
            {"t": idle_since, "id": stale.id},
        )
        db.commit()
        stale_id, fresh_id = stale.id, fresh.id
    finally:
        db.close()

    asyncio.run(jobs.sweep_stale_conversations())

    swept = _conversation(stale_id)
    assert swept.status == "ended"
    assert abs((swept.ended_at - idle_since).total_seconds()) < 1
    assert _conversation(fresh_id).status == "active"
