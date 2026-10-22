import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api import routes_schedule
from app.api.deps import get_current_admin
from app.db.session import SessionLocal
from app.main import app
from app.models.call_schedule import CallStatus
from app.repositories import call_schedule_repo, client_repo

TEST_EMAIL = "pytest.decline@example.invalid"


@pytest.fixture
def deleted_rooms(monkeypatch):
    rooms: list[str] = []

    async def _fake_delete_room(name: str) -> None:
        rooms.append(name)

    monkeypatch.setattr(routes_schedule, "delete_room", _fake_delete_room)
    return rooms


@pytest.fixture
def api():
    app.dependency_overrides[get_current_admin] = lambda: "pytest"
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_admin, None)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        ids = "(select id from clients where email = :e)"
        p = {"e": TEST_EMAIL}
        db.execute(text(f"delete from call_schedule where client_id in {ids}"), p)
        db.execute(text("delete from clients where email = :e"), p)
        db.commit()
    finally:
        db.close()


def _entry(status: CallStatus, *, answered: bool = False) -> uuid.UUID:
    db = SessionLocal()
    try:
        client = client_repo.get_or_create_by_email(
            db, full_name="Pytest Decline", email=TEST_EMAIL, phone=None
        )
        entry = call_schedule_repo.create(
            db, client_id=client.id, scheduled_at=datetime.now(timezone.utc)
        )
        call_schedule_repo.update_fields(
            db,
            entry,
            {
                "status": status,
                "livekit_room_name": f"coldcall-{entry.id}",
                "answered_at": datetime.now(timezone.utc) if answered else None,
            },
        )
        return entry.id
    finally:
        db.close()


def _status(entry_id: uuid.UUID) -> CallStatus:
    db = SessionLocal()
    try:
        return call_schedule_repo.get(db, entry_id).status
    finally:
        db.close()


def test_decline_cancels_ringing_call_and_deletes_room(api, deleted_rooms):
    entry_id = _entry(CallStatus.in_progress)
    res = api.post(f"/api/schedule/{entry_id}/decline", json={"reason": "cancelled"})
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    assert res.json()["outcome"] == "declined by callee"
    assert _status(entry_id) == CallStatus.cancelled
    assert deleted_rooms == [f"coldcall-{entry_id}"]


def test_unanswered_call_marked_missed(api, deleted_rooms):
    entry_id = _entry(CallStatus.dispatched)
    res = api.post(f"/api/schedule/{entry_id}/decline", json={"reason": "missed"})
    assert res.status_code == 200
    assert _status(entry_id) == CallStatus.missed


@pytest.mark.parametrize("status", [CallStatus.pending, CallStatus.completed, CallStatus.cancelled])
def test_decline_rejected_when_not_ringing(api, deleted_rooms, status):
    entry_id = _entry(status)
    res = api.post(f"/api/schedule/{entry_id}/decline", json={"reason": "cancelled"})
    assert res.status_code == 409
    assert _status(entry_id) == status
    assert deleted_rooms == []


@pytest.mark.parametrize("reason", ["cancelled", "missed"])
def test_decline_rejected_when_answered(api, deleted_rooms, reason):
    # e.g. a second dashboard tab still ringing/timing out after the call was
    # picked up elsewhere -- must not end the live conversation.
    entry_id = _entry(CallStatus.in_progress, answered=True)
    res = api.post(f"/api/schedule/{entry_id}/decline", json={"reason": reason})
    assert res.status_code == 409
    assert res.json()["detail"] == "Call was already answered"
    assert _status(entry_id) == CallStatus.in_progress
    assert deleted_rooms == []


def test_decline_unknown_call(api, deleted_rooms):
    res = api.post(f"/api/schedule/{uuid.uuid4()}/decline", json={"reason": "cancelled"})
    assert res.status_code == 404


def test_incoming_call_includes_agent_identity(api):
    entry_id = _entry(CallStatus.in_progress)
    res = api.get(f"/api/schedule/{entry_id}/incoming")
    assert res.status_code == 200
    body = res.json()
    assert body["client"]["full_name"] == "Pytest Decline"
    assert body["agent_display_name"]
    assert body["agency_name"]


def test_transition_does_not_overwrite_terminal_status():
    entry_id = _entry(CallStatus.cancelled)
    db = SessionLocal()
    try:
        changed = call_schedule_repo.transition(
            db,
            entry_id,
            from_statuses={CallStatus.dispatched, CallStatus.in_progress},
            values={"status": CallStatus.missed},
        )
    finally:
        db.close()
    assert changed is False
    assert _status(entry_id) == CallStatus.cancelled


def test_transition_unanswered_only_skips_answered_row():
    entry_id = _entry(CallStatus.in_progress, answered=True)
    db = SessionLocal()
    try:
        changed = call_schedule_repo.transition(
            db,
            entry_id,
            from_statuses={CallStatus.dispatched, CallStatus.in_progress},
            values={"status": CallStatus.missed},
            unanswered_only=True,
        )
    finally:
        db.close()
    assert changed is False
    assert _status(entry_id) == CallStatus.in_progress
