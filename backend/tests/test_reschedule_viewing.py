"""Viewing follow-up calls: the cold call loads the lead's upcoming viewing
(session_context), reschedule_viewing moves it, and the schedule lists every lead
with their viewing if any (routes_schedule). Real database; each test cleans up the clients it
created (bookings, invites and call rows go with them)."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from livekit.agents.llm import ToolError
from reserved_phone import delete_clients, unused_test_phone
from sqlalchemy import text

from app.agent import session_context
from app.agent.tools.reschedule_viewing import reschedule_viewing
from app.agent.userdata import Channel, SessionUserdata, UpcomingViewing
from app.api.deps import get_current_admin
from app.db.session import SessionLocal
from app.main import app
from app.models.booking import BookingChannel, BookingStatus
from app.models.call_schedule import CallStatus
from app.repositories import booking_repo, call_schedule_repo, client_repo
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


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _lead(
    *viewings: tuple[datetime, BookingStatus],
    scheduled_at: datetime | None = None,
    call_status: CallStatus | None = None,
):
    """A test client with these viewings, plus a call row (now unless
    `scheduled_at` is given); returns (client_id, [booking ids], call_schedule_id)."""
    db = SessionLocal()
    try:
        client = client_repo.get_or_create_by_phone(
            db, full_name="Pytest Viewing", phone=normalize_bd_mobile(unused_test_phone())
        )
        _created.append(client.id)
        booking_ids = []
        for when, status in viewings:
            booking = booking_repo.create(
                db,
                client_id=client.id,
                property_id=None,
                channel=BookingChannel.inbound_chat,
                proposed_datetime=when,
            )
            booking.status = status
            db.commit()
            booking_ids.append(booking.id)
        entry = call_schedule_repo.create(
            db, client_id=client.id, scheduled_at=scheduled_at or _now()
        )
        if call_status is not None:
            entry.status = call_status
            db.commit()
        return client.id, booking_ids, entry.id
    finally:
        db.close()


def _resolve(client_id, call_id) -> SessionUserdata:
    meta = json.dumps(
        {
            "channel": "outbound_coldcall",
            "client_id": str(client_id),
            "call_schedule_id": str(call_id),
        }
    )
    return session_context.resolve(meta, room=None)


# ---- session_context ----


def test_a_cold_call_loads_the_soonest_upcoming_viewing():
    soon, later = _now() + timedelta(days=1), _now() + timedelta(days=5)
    client_id, (later_id, soon_id, _), call_id = _lead(
        (later, BookingStatus.proposed),
        (soon, BookingStatus.confirmed),
        (_now() + timedelta(hours=1), BookingStatus.cancelled),
    )
    viewing = _resolve(client_id, call_id).upcoming_viewing
    assert viewing is not None
    assert viewing.booking_id == soon_id
    assert viewing.when == soon


def test_past_or_cancelled_viewings_are_not_followed_up():
    client_id, _, call_id = _lead(
        (_now() - timedelta(days=1), BookingStatus.proposed),
        (_now() + timedelta(days=1), BookingStatus.cancelled),
    )
    assert _resolve(client_id, call_id).upcoming_viewing is None


# ---- reschedule_viewing ----


def _ctx(client_id, booking_id, call_id, when) -> SimpleNamespace:
    userdata = SessionUserdata(
        channel=Channel.outbound_coldcall,
        room=None,
        client=SimpleNamespace(id=client_id),
        call_schedule_id=call_id,
        upcoming_viewing=UpcomingViewing(booking_id=booking_id, when=when),
    )
    return SimpleNamespace(userdata=userdata)


def test_reschedule_moves_the_viewing_and_tells_the_agency():
    old = _now() + timedelta(days=1)
    client_id, (booking_id,), call_id = _lead((old, BookingStatus.proposed))
    ctx = _ctx(client_id, booking_id, call_id, old)
    new = (_now() + timedelta(days=3)).replace(hour=4, minute=0, second=0)

    out = asyncio.run(reschedule_viewing(ctx, new_datetime=new.isoformat()))

    assert out.startswith("Viewing moved to ")
    assert ctx.userdata.upcoming_viewing.when == new
    db = SessionLocal()
    try:
        assert booking_repo.get(db, booking_id).proposed_datetime == new
        subjects = db.execute(
            text("select subject from meeting_invites where booking_id = :b"), {"b": booking_id}
        ).scalars().all()
        assert any(s.startswith("Viewing rescheduled: Pytest Viewing") for s in subjects)
        assert call_schedule_repo.get(db, call_id).outcome.startswith("viewing moved to ")
    finally:
        db.close()


def test_reschedule_refuses_a_cancelled_viewing_a_past_time_or_no_viewing():
    when = _now() + timedelta(days=1)
    client_id, (booking_id,), call_id = _lead((when, BookingStatus.cancelled))
    future = (_now() + timedelta(days=2)).replace(hour=5, minute=0, second=0).isoformat()  # 11 AM Dhaka
    with pytest.raises(ToolError):
        asyncio.run(reschedule_viewing(_ctx(client_id, booking_id, call_id, when), future))
    with pytest.raises(ToolError):
        asyncio.run(
            reschedule_viewing(
                _ctx(client_id, booking_id, call_id, when), new_datetime="2020-01-01T10:00:00"
            )
        )
    ctx = _ctx(client_id, booking_id, call_id, when)
    ctx.userdata.upcoming_viewing = None
    with pytest.raises(ToolError):
        asyncio.run(reschedule_viewing(ctx, new_datetime=future))


def test_reschedule_refuses_a_time_outside_viewing_hours():
    when = _now() + timedelta(days=1)
    client_id, (booking_id,), call_id = _lead((when, BookingStatus.proposed))
    # 15:00 UTC is 9 PM in Dhaka.
    late = (_now() + timedelta(days=3)).replace(hour=15, minute=0, second=0)
    with pytest.raises(ToolError) as exc:
        asyncio.run(reschedule_viewing(_ctx(client_id, booking_id, call_id, when), late.isoformat()))
    assert "8 AM to 6 PM" in exc.value.message


# ---- scheduling ----


def test_leads_lists_every_lead_with_its_upcoming_viewing_first(api):
    soon = _now() + timedelta(days=1)
    with_viewing, (booking_id,), _ = _lead((soon, BookingStatus.proposed))
    without, _, _ = _lead((_now() - timedelta(days=1), BookingStatus.proposed))

    listed = api.get("/api/schedule/leads").json()
    rows = {row["client"]["id"]: row for row in listed}

    assert rows[str(without)]["viewing"] is None
    viewing = rows[str(with_viewing)]["viewing"]
    assert viewing["booking_id"] == str(booking_id)
    assert datetime.fromisoformat(viewing["when"]) == soon
    assert viewing["property_title"] is None
    # Leads with a viewing come before those without.
    ids = [row["client"]["id"] for row in listed]
    assert ids.index(str(with_viewing)) < ids.index(str(without))


def test_any_lead_can_be_called_with_or_without_a_viewing(api):
    viewing = _now() + timedelta(days=1)
    client_id, _, call_id = _lead((viewing, BookingStatus.proposed))
    no_viewing, _, _ = _lead()

    def create(client, at: datetime):
        return api.post(
            "/api/schedule", json={"client_id": str(client), "scheduled_at": at.isoformat()}
        )

    assert create(client_id, viewing - timedelta(hours=2)).status_code == 201
    # After the viewing it's a plain cold call.
    assert create(client_id, viewing + timedelta(hours=1)).status_code == 201
    moved = api.patch(
        f"/api/schedule/{call_id}",
        json={"scheduled_at": (viewing + timedelta(hours=1)).isoformat()},
    )
    assert moved.status_code == 200
    assert create(no_viewing, _now() + timedelta(hours=1)).status_code == 201


def _listed_viewing(api, call_id):
    rows = {row["id"]: row for row in api.get("/api/schedule", params={"limit": 1000}).json()}
    return rows[str(call_id)]["viewing"]


def test_the_schedule_shows_which_open_calls_follow_up_a_viewing(api):
    # Call times are in the future so the scheduler can't claim these rows.
    call_at = _now() + timedelta(days=2)
    viewing = call_at + timedelta(days=1)
    followup, (booking_id,), followup_call = _lead(
        (viewing, BookingStatus.proposed), scheduled_at=call_at
    )
    _, _, cold_call = _lead(scheduled_at=call_at)

    listed = _listed_viewing(api, followup_call)
    assert listed["booking_id"] == str(booking_id)
    assert datetime.fromisoformat(listed["when"]) == viewing
    assert _listed_viewing(api, cold_call) is None


def test_the_schedule_skips_a_viewing_before_the_call_time(api):
    # Viewing A falls before the call, so the call follows up viewing B.
    call_at = _now() + timedelta(days=2)
    _, (_, b_id), call_id = _lead(
        (_now() + timedelta(days=1), BookingStatus.proposed),
        (_now() + timedelta(days=3), BookingStatus.proposed),
        scheduled_at=call_at,
    )
    assert _listed_viewing(api, call_id)["booking_id"] == str(b_id)


def test_a_finished_call_shows_no_viewing(api):
    _, _, call_id = _lead(
        (_now() + timedelta(days=3), BookingStatus.proposed),
        scheduled_at=_now() + timedelta(days=2),
        call_status=CallStatus.completed,
    )
    assert _listed_viewing(api, call_id) is None
