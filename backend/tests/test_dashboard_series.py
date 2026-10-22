from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.api.routes_dashboard import build_series, local_today, today_bounds, week_start
from app.config import get_settings
from app.db.session import SessionLocal
from app.repositories import conversation_repo

ROOM_PREFIX = "pytest-series-"
DHAKA = ZoneInfo("Asia/Dhaka")  # UTC+6, no DST
UTC = ZoneInfo("UTC")
# Far in the past, so real conversations never land in the tested buckets.
NOW = datetime(2001, 1, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = SessionLocal()
    try:
        db.execute(text("delete from conversations where room_name like :p"), {"p": ROOM_PREFIX + "%"})
        db.commit()
    finally:
        db.close()


def _conversation_at(started_at: datetime) -> None:
    db = SessionLocal()
    try:
        conversation = conversation_repo.create(
            db, channel="inbound_chat", room_name=f"{ROOM_PREFIX}{started_at.isoformat()}"
        )
        db.execute(
            text("update conversations set started_at = :t where id = :id"),
            {"t": started_at, "id": conversation.id},
        )
        db.commit()
    finally:
        db.close()


def test_today_bounds_follow_agency_timezone():
    # 20:00 UTC on the 15th is already 02:00 on the 16th in Dhaka.
    now = datetime(2001, 1, 15, 20, 0, tzinfo=timezone.utc)
    start, end = today_bounds(DHAKA, now)
    assert local_today(DHAKA, now) == date(2001, 1, 16)
    assert start == datetime(2001, 1, 15, 18, 0, tzinfo=timezone.utc)
    assert end - start == timedelta(days=1)
    # Same instant in UTC is still the 15th.
    assert today_bounds(UTC, now)[0] == datetime(2001, 1, 15, tzinfo=timezone.utc)


def test_week_starts_monday_local_midnight():
    # 2001-01-15 was a Monday; 19:00 UTC Sunday the 14th is already Monday in Dhaka.
    now = datetime(2001, 1, 14, 19, 0, tzinfo=timezone.utc)
    assert week_start(DHAKA, now) == datetime(2001, 1, 14, 18, 0, tzinfo=timezone.utc)
    assert week_start(UTC, now) == datetime(2001, 1, 8, tzinfo=timezone.utc)


def test_series_buckets_by_agency_timezone():
    # 00:30 Dhaka on the 15th = 18:30 UTC on the 14th.
    _conversation_at(datetime(2001, 1, 14, 18, 30, tzinfo=timezone.utc))
    # 23:30 Dhaka on the 14th = 17:30 UTC on the 14th.
    _conversation_at(datetime(2001, 1, 14, 17, 30, tzinfo=timezone.utc))
    # Before the 7-day window in either zone.
    _conversation_at(datetime(2001, 1, 1, 12, 0, tzinfo=timezone.utc))

    db = SessionLocal()
    try:
        dhaka = build_series(db, 7, DHAKA, NOW)
        utc = build_series(db, 7, UTC, NOW)
    finally:
        db.close()

    assert [p.date for p in dhaka] == [date(2001, 1, 9) + timedelta(days=i) for i in range(7)]
    assert {p.date: p.count for p in dhaka if p.count} == {date(2001, 1, 14): 1, date(2001, 1, 15): 1}
    assert {p.date: p.count for p in utc if p.count} == {date(2001, 1, 14): 2}


def test_series_endpoint(api):
    response = api.get("/api/dashboard/conversation-series", params={"range": "30d"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["timezone"] == get_settings().agency_timezone
    assert len(body["points"]) == 30
    tz = ZoneInfo(get_settings().agency_timezone)
    assert body["points"][-1]["date"] == local_today(tz).isoformat()
    assert body["total"] == sum(p["count"] for p in body["points"])
    assert api.get("/api/dashboard/conversation-series", params={"range": "1y"}).status_code == 422


def test_summary_counts_conversations_today(api):
    before = api.get("/api/dashboard/summary").json()["conversations_today"]
    _conversation_at(datetime.now(timezone.utc))
    assert api.get("/api/dashboard/summary").json()["conversations_today"] == before + 1


def test_recent_endpoints(api):
    _conversation_at(datetime.now(timezone.utc))
    recent = api.get("/api/dashboard/recent-conversations", params={"limit": 3}).json()
    assert 1 <= len(recent) <= 3
    assert recent[0]["room_name"].startswith(ROOM_PREFIX)


@pytest.mark.parametrize(
    "path",
    [
        "/api/dashboard/summary",
        "/api/dashboard/conversation-series",
        "/api/dashboard/recent-conversations",
    ],
)
def test_dashboard_routes_need_auth(anon_api, path):
    assert anon_api.get(path).status_code == 401


def test_summary_has_no_real_estate_fields(api):
    body = api.get("/api/dashboard/summary").json()
    assert "active_listings" not in body and "pending_calls_today" not in body
