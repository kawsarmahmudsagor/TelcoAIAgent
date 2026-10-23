from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.bss import notifications
from app.models.telco import (
    Balance,
    Notification,
    NotificationKind,
    PlanType,
    SubscriberStatus,
)

NOW = datetime.now(timezone.utc)


def _count(db, sub):
    return db.scalar(
        select(func.count()).select_from(Notification).where(Notification.subscriber_id == sub.id)
    )


def _rows(db, sub, kind):
    return list(
        db.scalars(
            select(Notification).where(
                Notification.subscriber_id == sub.id, Notification.kind == kind
            )
        )
    )


def _sweep(db):
    # Other rows in the dev DB may fire too; tests assert on their own subscriber.
    return notifications.run_sweep(db)


def test_pack_expiring_fires_within_3_days_without_auto_renew(db, bss_world):
    sub = bss_world.subscriber()
    pkg = bss_world.package()
    s = bss_world.subscription(sub, pkg, expires_in_days=2, auto_renew=False)
    counts = _sweep(db)
    assert counts["pack_expiring"] >= 1
    rows = _rows(db, sub, NotificationKind.pack_expiring)
    assert len(rows) == 1
    assert rows[0].subject_key == str(s.id)
    assert rows[0].payload == {"package_name": pkg.name, "expires_at": s.expires_at.isoformat()}


def test_pack_expiring_skips_auto_renew_and_far_expiry(db, bss_world):
    sub = bss_world.subscriber()
    pkg = bss_world.package()
    bss_world.subscription(sub, pkg, expires_in_days=2, auto_renew=True)
    bss_world.subscription(sub, pkg, expires_in_days=4, auto_renew=False)
    _sweep(db)
    assert _rows(db, sub, NotificationKind.pack_expiring) == []


def test_low_balance_prepaid_only(db, bss_world):
    low = bss_world.subscriber(main_balance=Decimal("49.99"))
    edge = bss_world.subscriber(main_balance=Decimal("50"))
    post = bss_world.subscriber(plan_type=PlanType.postpaid, main_balance=Decimal("10"))
    _sweep(db)
    rows = _rows(db, low, NotificationKind.low_balance)
    assert len(rows) == 1
    assert rows[0].payload == {"balance": 49.99}
    assert _count(db, edge) == 0
    assert _count(db, post) == 0


def test_low_data_under_10_percent(db, bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("500"))
    other = bss_world.subscriber(main_balance=Decimal("500"))
    voice = bss_world.subscriber(main_balance=Decimal("500"))
    big = bss_world.package(data_mb=10240)
    vp = bss_world.package(minutes=300)
    s = bss_world.subscription(sub, big, data_left_mb=1000)
    bss_world.subscription(other, big, data_left_mb=1100)
    bss_world.subscription(voice, vp)
    _sweep(db)
    rows = _rows(db, sub, NotificationKind.low_data)
    assert len(rows) == 1
    assert rows[0].subject_key == str(s.id)
    assert rows[0].payload == {"package_name": big.name, "data_left_mb": 1000}
    assert _count(db, other) == 0
    assert _count(db, voice) == 0


def test_suspended_subscriber_gets_none(db, bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("1"), status=SubscriberStatus.suspended)
    pkg = bss_world.package(data_mb=1000)
    bss_world.subscription(sub, pkg, expires_in_days=1, data_left_mb=1)
    _sweep(db)
    assert _count(db, sub) == 0


def test_sweep_is_idempotent(db, bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("10"))
    pkg = bss_world.package(data_mb=1000)
    bss_world.subscription(sub, pkg, expires_in_days=1, data_left_mb=10)
    _sweep(db)
    assert _count(db, sub) == 3
    counts = _sweep(db)
    assert counts == {"pack_expiring": 0, "low_balance": 0, "low_data": 0}
    assert _count(db, sub) == 3


def test_notify_conflict_is_silent(db, bss_world):
    sub = bss_world.subscriber()
    args = (db, sub.id, NotificationKind.case_update, "TC-1:resolved", {"case_ref": "TC-1"})
    assert notifications.notify(*args) is True
    assert notifications.notify(*args) is False
    db.commit()
    assert _count(db, sub) == 1


def _seed_two(db, sub):
    notifications.notify(db, sub.id, NotificationKind.low_balance, "2026-01-01", {"balance": 32})
    notifications.notify(
        db, sub.id, NotificationKind.case_update, "TC-1:resolved",
        {"case_ref": "TC-1", "status": "resolved"},
    )
    db.commit()


def test_list_and_mark_read(db, bss_world, customer_api):
    sub = bss_world.subscriber()
    _seed_two(db, sub)
    api = customer_api(sub.id)
    body = api.get("/api/me/notifications").json()
    assert body["unread"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["title"] and body["items"][0]["body"]
    nid = body["items"][0]["id"]
    r = api.post(f"/api/me/notifications/{nid}/read")
    assert r.status_code == 200
    assert r.json()["read_at"] is not None
    assert r.headers["cache-control"] == "no-store"
    assert api.get("/api/me/notifications").json()["unread"] == 1
    assert api.post("/api/me/notifications/read-all").json() == {"updated": 1}
    assert api.get("/api/me/notifications").json()["unread"] == 0


def test_cannot_read_other_subscribers_notification(db, bss_world, customer_api):
    owner = bss_world.subscriber()
    other = bss_world.subscriber()
    _seed_two(db, owner)
    nid = db.scalars(select(Notification).where(Notification.subscriber_id == owner.id)).first().id
    r = customer_api(other.id).post(f"/api/me/notifications/{nid}/read")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "notification_not_found"
    db.expire_all()
    assert db.get(Notification, nid).read_at is None


def test_notifications_need_customer(api, anon_api):
    import uuid

    paths = [
        ("get", "/api/me/notifications"),
        ("post", f"/api/me/notifications/{uuid.uuid4()}/read"),
        ("post", "/api/me/notifications/read-all"),
    ]
    for client in (api, anon_api):
        for method, path in paths:
            assert getattr(client, method)(path).status_code == 401
