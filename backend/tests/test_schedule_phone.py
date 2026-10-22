import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api import routes_schedule
from app.api.deps import get_current_admin
from app.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.booking import BookingChannel
from app.models.call_schedule import CallStatus
from app.repositories import booking_repo, call_schedule_repo, client_repo

TEST_EMAIL = "pytest.phone@example.invalid"
MY_PHONE = "+8801711234567"


@pytest.fixture
def deleted_rooms(monkeypatch):
    rooms: list[str] = []

    async def _fake_delete_room(name: str) -> None:
        rooms.append(name)

    monkeypatch.setattr(routes_schedule, "delete_room", _fake_delete_room)
    return rooms


@pytest.fixture
def phone_settings(monkeypatch):
    settings = get_settings().model_copy(
        update={"sip_dial_allowlist": MY_PHONE, "sip_outbound_trunk_id": "ST_test"}
    )
    monkeypatch.setattr(routes_schedule, "get_settings", lambda: settings)
    return settings


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


def _client_id() -> uuid.UUID:
    """The test lead, with a viewing booked after any call these tests schedule
    (a call can only be scheduled for a lead with one)."""
    db = SessionLocal()
    try:
        client_id = client_repo.get_or_create_by_email(
            db, full_name="Pytest Phone", email=TEST_EMAIL, phone=None
        ).id
        after = datetime.now(timezone.utc) + timedelta(hours=2)
        if booking_repo.next_upcoming_for_client(db, client_id, after) is None:
            booking_repo.create(
                db,
                client_id=client_id,
                property_id=None,
                channel=BookingChannel.outbound_coldcall,
                proposed_datetime=datetime.now(timezone.utc) + timedelta(days=1),
            )
        return client_id
    finally:
        db.close()


def _entry(status: CallStatus, dial_number: str | None = MY_PHONE) -> uuid.UUID:
    db = SessionLocal()
    try:
        entry = call_schedule_repo.create(
            db,
            client_id=_client_id(),
            scheduled_at=datetime.now(timezone.utc),
            dial_number=dial_number,
        )
        call_schedule_repo.update_fields(
            db, entry, {"status": status, "livekit_room_name": f"coldcall-{entry.id}"}
        )
        return entry.id
    finally:
        db.close()


def _get(entry_id: uuid.UUID):
    db = SessionLocal()
    try:
        return call_schedule_repo.get(db, entry_id)
    finally:
        db.close()


def _create(api, dial_number):
    return api.post(
        "/api/schedule",
        json={
            "client_id": str(_client_id()),
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "dial_number": dial_number,
        },
    )


def test_create_with_allowed_number_stores_e164(api, phone_settings):
    res = _create(api, "01711-234567")
    assert res.status_code == 201
    assert res.json()["dial_number"] == MY_PHONE


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_dial_number_is_browser_call(api, phone_settings, blank):
    res = _create(api, blank)
    assert res.status_code == 201
    assert res.json()["dial_number"] is None


def test_number_off_allowlist_rejected(api, phone_settings):
    res = _create(api, "+8801922345678")
    assert res.status_code == 400
    assert "SIP_DIAL_ALLOWLIST" in res.json()["detail"]


def test_invalid_number_rejected(api, phone_settings):
    res = _create(api, "hello")
    assert res.status_code == 400
    assert isinstance(res.json()["detail"], str)


def test_phone_call_rejected_when_trunk_not_configured(api, monkeypatch):
    settings = get_settings().model_copy(
        update={"sip_dial_allowlist": MY_PHONE, "sip_outbound_trunk_id": ""}
    )
    monkeypatch.setattr(routes_schedule, "get_settings", lambda: settings)
    res = _create(api, MY_PHONE)
    assert res.status_code == 400
    assert "SIP_OUTBOUND_TRUNK_ID" in res.json()["detail"]


def test_phone_call_has_no_browser_incoming_screen(api, deleted_rooms):
    entry_id = _entry(CallStatus.in_progress)
    assert api.get(f"/api/schedule/{entry_id}/incoming").status_code == 409
    res = api.post(f"/api/schedule/{entry_id}/decline", json={"reason": "cancelled"})
    assert res.status_code == 409
    assert _get(entry_id).status == CallStatus.in_progress
    assert deleted_rooms == []


@pytest.mark.parametrize("status", [CallStatus.dispatched, CallStatus.in_progress])
def test_hangup_cancels_live_call_and_deletes_room(api, deleted_rooms, status):
    entry_id = _entry(status)
    res = api.post(f"/api/schedule/{entry_id}/hangup")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    assert _get(entry_id).outcome == "ended from dashboard"
    assert deleted_rooms == [f"coldcall-{entry_id}"]


def test_hangup_rejected_when_not_live(api, deleted_rooms):
    entry_id = _entry(CallStatus.completed)
    assert api.post(f"/api/schedule/{entry_id}/hangup").status_code == 409
    assert deleted_rooms == []


def test_delete_live_call_tears_room_down(api, deleted_rooms):
    entry_id = _entry(CallStatus.in_progress)
    assert api.delete(f"/api/schedule/{entry_id}").status_code == 204
    assert deleted_rooms == [f"coldcall-{entry_id}"]
    assert _get(entry_id) is None


def test_delete_pending_call_leaves_rooms_alone(api, deleted_rooms):
    entry_id = _entry(CallStatus.pending)
    assert api.delete(f"/api/schedule/{entry_id}").status_code == 204
    assert deleted_rooms == []


def test_list_includes_dial_number(api):
    entry_id = _entry(CallStatus.pending)
    rows = {row["id"]: row for row in api.get("/api/schedule").json()}
    assert rows[str(entry_id)]["dial_number"] == MY_PHONE
