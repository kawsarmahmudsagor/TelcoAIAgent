import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.repositories import client_repo, conversation_repo

ROOM_PREFIX = "pytest-conv-api-"
TEST_EMAIL = "pytest.conversations@example.invalid"


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


def _conversation(*, channel: str = "inbound_chat", with_client: bool = False) -> uuid.UUID:
    db = SessionLocal()
    try:
        client_id = None
        if with_client:
            client_id = client_repo.get_or_create_by_email(
                db, full_name="Pytest Conversations", email=TEST_EMAIL, phone="+8801700000000"
            ).id
        conversation = conversation_repo.create(
            db,
            channel=channel,
            room_name=f"{ROOM_PREFIX}{uuid.uuid4().hex[:8]}",
            client_id=client_id,
        )
        now = datetime.now(timezone.utc)
        conversation_repo.add_message(
            db, conversation.id, seq=1, role="assistant", text="Hello!", created_at=now
        )
        conversation_repo.add_message(
            db, conversation.id, seq=2, role="user", text="Any flats in Banani?", created_at=now
        )
        conversation_repo.add_message(
            db,
            conversation.id,
            seq=3,
            role="tool",
            text="Found 2 listings",
            tool_name="search_apartments",
            tool_args={"location": "Banani"},
            created_at=now,
        )
        return conversation.id
    finally:
        db.close()


def test_list_filters_and_preview(api):
    chat_id = _conversation(with_client=True)
    call_id = _conversation(channel="outbound_coldcall")

    body = api.get("/api/conversations", params={"channel": "inbound_chat", "limit": 200}).json()
    ids = {item["id"] for item in body["items"]}
    assert str(chat_id) in ids and str(call_id) not in ids
    item = next(i for i in body["items"] if i["id"] == str(chat_id))
    assert item["preview"] == "Any flats in Banani?"
    assert item["client_name"] == "Pytest Conversations"
    assert item["message_count"] == 3

    page = api.get("/api/conversations", params={"status": "active", "limit": 1}).json()
    assert len(page["items"]) == 1 and page["total"] >= 2
    assert api.get("/api/conversations", params={"status": "bogus"}).status_code == 422


def test_detail_has_ordered_transcript(api):
    conversation_id = _conversation(with_client=True)
    body = api.get(f"/api/conversations/{conversation_id}").json()
    assert [m["seq"] for m in body["messages"]] == [1, 2, 3]
    assert body["messages"][2]["tool_args"] == {"location": "Banani"}
    assert body["client_email"] == TEST_EMAIL
    assert api.get(f"/api/conversations/{uuid.uuid4()}").status_code == 404


def test_delete_and_bulk_delete(api):
    one, two, three = (_conversation() for _ in range(3))
    assert api.delete(f"/api/conversations/{one}").status_code == 204
    assert api.delete(f"/api/conversations/{one}").status_code == 404
    response = api.post(
        "/api/conversations/bulk-delete", json={"ids": [str(two), str(three), str(uuid.uuid4())]}
    )
    assert response.json() == {"deleted": 2}
    db = SessionLocal()
    try:
        # Messages go with their conversation (ON DELETE CASCADE).
        assert conversation_repo.list_messages(db, two) == []
    finally:
        db.close()
    assert api.post("/api/conversations/bulk-delete", json={"ids": []}).status_code == 422


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/conversations"),
        ("get", f"/api/conversations/{uuid.uuid4()}"),
        ("delete", f"/api/conversations/{uuid.uuid4()}"),
        ("post", "/api/conversations/bulk-delete"),
    ],
)
def test_conversation_routes_need_auth(anon_api, method, path):
    kwargs = {"json": {"ids": [str(uuid.uuid4())]}} if method == "post" else {}
    assert getattr(anon_api, method)(path, **kwargs).status_code == 401
