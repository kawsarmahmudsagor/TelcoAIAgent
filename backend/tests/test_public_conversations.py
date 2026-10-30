import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.agent import session_context
from app.agent.transcript import TranscriptRecorder, load_resume_history
from app.agent.userdata import Channel, SessionUserdata
from app.api.deps import get_optional_subscriber
from app.db.session import SessionLocal
from app.main import app
from app.repositories import conversation_repo

ROOM_PREFIX = "pytest-visitor-conv-"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        db.execute(text("delete from conversations where room_name like :p"), {"p": ROOM_PREFIX + "%"})
        db.commit()
    finally:
        db.close()


def _room() -> str:
    return f"{ROOM_PREFIX}{uuid.uuid4().hex[:8]}"


def _conversation(
    visitor_id: uuid.UUID | None,
    *,
    first_user_text: str | None = "Any flats in Banani?",
    channel: str = "inbound_chat",
    is_phone_call: bool = False,
    started_minutes_ago: int = 0,
    room_name: str | None = None,
    subscriber_id: uuid.UUID | None = None,
) -> uuid.UUID:
    db = SessionLocal()
    try:
        conversation = conversation_repo.create(
            db,
            channel=channel,
            room_name=room_name or _room(),
            is_phone_call=is_phone_call,
            visitor_id=visitor_id,
            subscriber_id=subscriber_id,
        )
        started = datetime.now(timezone.utc) - timedelta(minutes=started_minutes_ago)
        db.execute(
            text("update conversations set started_at = :s where id = :i"),
            {"s": started, "i": conversation.id},
        )
        db.commit()
        conversation_repo.add_message(
            db, conversation.id, seq=1, role="assistant", text="Hello!", created_at=started
        )
        if first_user_text is not None:
            conversation_repo.add_message(
                db, conversation.id, seq=2, role="user", text=first_user_text, created_at=started
            )
            conversation_repo.add_message(
                db,
                conversation.id,
                seq=3,
                role="tool",
                text="Found 2 listings",
                tool_name="search_apartments",
                tool_args={"location": "Banani"},
                created_at=started,
            )
            conversation_repo.add_message(
                db, conversation.id, seq=4, role="assistant", text="Two of them.", created_at=started
            )
        return conversation.id
    finally:
        db.close()


def _headers(visitor_id: uuid.UUID | str) -> dict[str, str]:
    return {"X-Visitor-Id": str(visitor_id)}


def test_lists_only_this_visitors_chats_newest_first_and_paginates(anon_api):
    visitor, other = uuid.uuid4(), uuid.uuid4()
    oldest = _conversation(visitor, first_user_text="first", started_minutes_ago=30)
    middle = _conversation(visitor, first_user_text="second", started_minutes_ago=20)
    newest = _conversation(visitor, first_user_text="third", started_minutes_ago=10)
    latest = _conversation(visitor, first_user_text="fourth", started_minutes_ago=5)
    _conversation(other)
    _conversation(visitor, is_phone_call=True)
    _conversation(visitor, channel="outbound_coldcall")
    _conversation(visitor, first_user_text=None)  # greeting only: not listed
    _conversation(None)

    first = anon_api.get("/api/public/conversations", headers=_headers(visitor)).json()
    assert first["total"] == 4 and first["limit"] == 3 and first["offset"] == 0
    assert [i["id"] for i in first["items"]] == [str(latest), str(newest), str(middle)]
    item = first["items"][0]
    assert item["preview"] == "fourth"
    assert item["message_count"] == 3  # tool rows aren't counted
    assert set(item) == {"id", "started_at", "ended_at", "status", "preview", "message_count", "reply_language"}

    rest = anon_api.get(
        "/api/public/conversations", params={"offset": 3}, headers=_headers(visitor)
    ).json()
    assert [i["id"] for i in rest["items"]] == [str(oldest)]


def test_excludes_the_current_room(anon_api):
    visitor = uuid.uuid4()
    current_room = _room()
    _conversation(visitor, room_name=current_room)
    earlier = _conversation(visitor, started_minutes_ago=5)
    body = anon_api.get(
        "/api/public/conversations",
        params={"exclude_room": current_room},
        headers=_headers(visitor),
    ).json()
    assert [i["id"] for i in body["items"]] == [str(earlier)] and body["total"] == 1


def test_detail_hides_tool_rows_and_other_visitors(anon_api):
    visitor = uuid.uuid4()
    conversation_id = _conversation(visitor)
    response = anon_api.get(f"/api/public/conversations/{conversation_id}", headers=_headers(visitor))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert [(m["seq"], m["role"]) for m in body["messages"]] == [
        (1, "assistant"),
        (2, "user"),
        (4, "assistant"),
    ]
    assert "room_name" not in body and "subscriber_id" not in body

    for path in (f"/api/public/conversations/{conversation_id}", "/api/public/conversations/nope"):
        assert anon_api.get(path, headers=_headers(uuid.uuid4())).status_code == 404
    phone = _conversation(visitor, is_phone_call=True)
    assert anon_api.get(f"/api/public/conversations/{phone}", headers=_headers(visitor)).status_code == 404


@pytest.fixture
def signed_in_api(anon_api):
    """Factory: signed_in_api(subscriber_id) -> client whose portal cookie verifies."""

    def make(subscriber_id):
        app.dependency_overrides[get_optional_subscriber] = lambda: subscriber_id
        return anon_api

    yield make
    app.dependency_overrides.pop(get_optional_subscriber, None)


def test_logged_in_sees_own_chats_and_this_browsers_guest_chats(bss_world, signed_in_api, anon_api):
    a, b = bss_world.subscriber(), bss_world.subscriber()
    visitor = uuid.uuid4()
    guest = _conversation(visitor, started_minutes_ago=30)
    a_elsewhere = _conversation(uuid.uuid4(), subscriber_id=a.id, started_minutes_ago=20)
    b_here = _conversation(visitor, subscriber_id=b.id, started_minutes_ago=10)

    # A guest never sees an account's chats, even ones from this browser.
    body = anon_api.get("/api/public/conversations", headers=_headers(visitor)).json()
    assert [i["id"] for i in body["items"]] == [str(guest)]
    assert anon_api.get(f"/api/public/conversations/{b_here}", headers=_headers(visitor)).status_code == 404

    client = signed_in_api(a.id)
    body = client.get("/api/public/conversations", headers=_headers(visitor)).json()
    assert [i["id"] for i in body["items"]] == [str(a_elsewhere), str(guest)]
    assert client.get(f"/api/public/conversations/{a_elsewhere}", headers=_headers(visitor)).status_code == 200
    assert client.get(f"/api/public/conversations/{b_here}", headers=_headers(visitor)).status_code == 404


@pytest.mark.parametrize("headers", [{}, {"X-Visitor-Id": "not-a-uuid"}, {"X-Visitor-Id": ""}])
def test_needs_a_valid_visitor_id(anon_api, headers):
    assert anon_api.get("/api/public/conversations", headers=headers).status_code == 422
    path = f"/api/public/conversations/{uuid.uuid4()}"
    assert anon_api.get(path, headers=headers).status_code == 422


def test_limit_is_capped(anon_api):
    headers = _headers(uuid.uuid4())
    assert anon_api.get("/api/public/conversations", params={"limit": 21}, headers=headers).status_code == 422
    assert anon_api.get("/api/public/conversations", params={"limit": 0}, headers=headers).status_code == 422


# --- the agent side: dispatch metadata -> SessionUserdata -> conversation row ----


def test_session_context_takes_a_valid_visitor_id_only():
    visitor = uuid.uuid4()
    chat = session_context.resolve(
        json.dumps({"channel": "inbound_chat", "visitor_id": str(visitor)}), None
    )
    assert chat.visitor_id == visitor
    for meta in (
        {"channel": "inbound_chat", "visitor_id": "not-a-uuid"},
        {"channel": "inbound_chat", "visitor_id": 42},
        {"channel": "inbound_chat"},
    ):
        assert session_context.resolve(json.dumps(meta), None).visitor_id is None, meta


def test_transcript_recorder_stores_the_visitor_id():
    class _Session:
        def on(self, *_args) -> None:
            pass

    visitor = uuid.uuid4()
    userdata = SessionUserdata(channel=Channel.inbound_chat, room=None, visitor_id=visitor)

    async def run() -> uuid.UUID:
        recorder = await TranscriptRecorder.start(_Session(), userdata, _room())
        assert recorder is not None
        await recorder.close()
        return recorder.conversation_id

    conversation_id = asyncio.run(run())
    db = SessionLocal()
    try:
        assert conversation_repo.get(db, conversation_id).visitor_id == visitor
    finally:
        db.close()


# --- carrying on an earlier conversation -------------------------------------------


def test_session_context_takes_a_valid_resume_id_only():
    conversation_id = uuid.uuid4()
    meta = {"channel": "inbound_chat", "resume_conversation_id": str(conversation_id)}
    assert session_context.resolve(json.dumps(meta), None).resume_conversation_id == conversation_id
    meta["resume_conversation_id"] = "nope"
    assert session_context.resolve(json.dumps(meta), None).resume_conversation_id is None


def test_load_resume_history_only_for_the_owner(bss_world):
    visitor = uuid.uuid4()
    conversation_id = _conversation(visitor)
    userdata = SessionUserdata(
        channel=Channel.inbound_chat, room=None, visitor_id=visitor, resume_conversation_id=conversation_id
    )
    load_resume_history(userdata)
    assert userdata.resume_conversation_id == conversation_id
    assert userdata.resume_history == [
        ("assistant", "Hello!"),
        ("user", "Any flats in Banani?"),
        ("assistant", "Two of them."),
    ]

    owner = bss_world.subscriber()
    owned = _conversation(visitor, subscriber_id=owner.id)
    for other_visitor, target in (
        (uuid.uuid4(), conversation_id),  # another browser's guest chat
        (visitor, owned),  # an account's chat on this browser, reopened by a guest
    ):
        stranger = SessionUserdata(
            channel=Channel.inbound_chat, room=None, visitor_id=other_visitor, resume_conversation_id=target
        )
        load_resume_history(stranger)
        assert stranger.resume_conversation_id is None and stranger.resume_history == []


def test_transcript_recorder_reopens_the_resumed_conversation():
    class _Session:
        def on(self, *_args) -> None:
            pass

    visitor = uuid.uuid4()
    conversation_id = _conversation(visitor)
    db = SessionLocal()
    try:
        conversation_repo.end(db, conversation_id)
    finally:
        db.close()
    userdata = SessionUserdata(
        channel=Channel.inbound_chat, room=None, visitor_id=visitor, resume_conversation_id=conversation_id
    )
    new_room = _room()

    async def run() -> TranscriptRecorder:
        recorder = await TranscriptRecorder.start(_Session(), userdata, new_room)
        assert recorder is not None
        return recorder

    recorder = asyncio.run(run())
    assert recorder.conversation_id == conversation_id == userdata.conversation_id
    assert recorder._seq == 4  # new messages are numbered after the old ones
    db = SessionLocal()
    try:
        conversation = conversation_repo.get(db, conversation_id)
        assert conversation.status == "active" and conversation.ended_at is None
        assert conversation.room_name == new_room
    finally:
        db.close()


def _set_language(conversation_id: uuid.UUID, lang: str | None) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text("update conversations set reply_language = :l where id = :i"),
            {"l": lang, "i": conversation_id},
        )
        db.commit()
    finally:
        db.close()


def _stored_language(conversation_id: uuid.UUID) -> str | None:
    db = SessionLocal()
    try:
        return conversation_repo.get(db, conversation_id).reply_language
    finally:
        db.close()


def test_history_returns_reply_language(anon_api):
    visitor = uuid.uuid4()
    conversation_id = _conversation(visitor)
    _set_language(conversation_id, "bn")
    body = anon_api.get("/api/public/conversations", headers=_headers(visitor)).json()
    assert body["items"][0]["reply_language"] == "bn"
    detail = anon_api.get(
        f"/api/public/conversations/{conversation_id}", headers=_headers(visitor)
    ).json()
    assert detail["reply_language"] == "bn"


def test_resume_keeps_stored_language():
    visitor = uuid.uuid4()
    conversation_id = _conversation(visitor)
    _set_language(conversation_id, "bn")
    userdata = SessionUserdata(
        channel=Channel.inbound_chat,
        room=None,
        visitor_id=visitor,
        resume_conversation_id=conversation_id,
        reply_language="en",
    )
    load_resume_history(userdata)
    assert userdata.reply_language == "bn"


def test_resume_legacy_row_takes_pick():
    visitor = uuid.uuid4()
    conversation_id = _conversation(visitor)
    userdata = SessionUserdata(
        channel=Channel.inbound_chat,
        room=None,
        visitor_id=visitor,
        resume_conversation_id=conversation_id,
        reply_language="en",
    )
    load_resume_history(userdata)
    assert userdata.reply_language == "en"

    class _Session:
        def on(self, *_):
            pass

    async def run():
        recorder = await TranscriptRecorder.start(_Session(), userdata, _room())
        await recorder.close()

    asyncio.run(run())
    assert _stored_language(conversation_id) == "en"
