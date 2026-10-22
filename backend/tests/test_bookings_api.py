"""POST /api/bookings: a viewing booked by hand on the dashboard for an existing
lead. Real database; each test cleans up the clients it created (bookings and
invites go with them)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from reserved_phone import delete_clients, unused_test_phone
from sqlalchemy import text

from app.api.deps import get_current_admin
from app.db.session import SessionLocal
from app.main import app
from app.repositories import client_repo, invite_repo
from app.services.phone_numbers import normalize_bd_mobile

_created: list = []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    delete_clients(_created)
    _created.clear()


@pytest.fixture
def api():
    app.dependency_overrides[get_current_admin] = lambda: "pytest"
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_admin, None)


def _lead() -> str:
    db = SessionLocal()
    try:
        client = client_repo.get_or_create_by_phone(
            db, full_name="Pytest Dashboard", phone=normalize_bd_mobile(unused_test_phone())
        )
        _created.append(client.id)
        return str(client.id)
    finally:
        db.close()


def _property() -> dict:
    db = SessionLocal()
    try:
        row = db.execute(
            text("select id, title from properties where is_active order by price limit 1")
        ).one()
        return {"id": str(row.id), "title": row.title}
    finally:
        db.close()


def _local(days: int, hour: int) -> str:
    # No UTC offset: read as agency local time.
    day = datetime.now(timezone.utc) + timedelta(days=days)
    return day.strftime(f"%Y-%m-%dT{hour:02d}:00:00")


def test_books_a_viewing_for_a_lead(api):
    client_id, prop = _lead(), _property()
    res = api.post(
        "/api/bookings",
        json={"client_id": client_id, "property_id": prop["id"], "proposed_datetime": _local(3, 11)},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["channel"] == "dashboard"
    assert body["client_id"] == client_id
    assert body["property_id"] == prop["id"]
    assert body["client_name"] == "Pytest Dashboard"

    db = SessionLocal()
    try:
        assert invite_repo.list_for_booking(db, body["id"])
    finally:
        db.close()

    # The lead now shows on the call schedule with this viewing.
    leads = {row["client"]["id"]: row for row in api.get("/api/schedule/leads").json()}
    assert leads[client_id]["viewing"]["booking_id"] == body["id"]
    assert leads[client_id]["viewing"]["property_title"] == prop["title"]


def test_property_is_optional(api):
    res = api.post(
        "/api/bookings", json={"client_id": _lead(), "proposed_datetime": _local(3, 11)}
    )
    assert res.status_code == 201, res.text
    assert res.json()["property_id"] is None


def test_refuses_past_or_out_of_hours_times(api):
    client_id = _lead()
    past = api.post(
        "/api/bookings", json={"client_id": client_id, "proposed_datetime": _local(-1, 11)}
    )
    assert past.status_code == 400
    late = api.post(
        "/api/bookings", json={"client_id": client_id, "proposed_datetime": _local(3, 22)}
    )
    assert late.status_code == 400
    assert "Viewings run from" in late.json()["detail"]


def test_unknown_lead_or_property_is_404(api):
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        api.post(
            "/api/bookings", json={"client_id": missing, "proposed_datetime": _local(3, 11)}
        ).status_code
        == 404
    )
    assert (
        api.post(
            "/api/bookings",
            json={"client_id": _lead(), "property_id": missing, "proposed_datetime": _local(3, 11)},
        ).status_code
        == 404
    )
