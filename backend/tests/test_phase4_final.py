"""Final-review fixes for Phase 4: MSISDN masking, status words, rules, bounds."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.api import routes_admin
from app.bss import audit, cases, monitor, network, notifications, ops, otp, recharge
from app.bss.types import RechargeRequest
from app.models.telco import (
    Actor,
    CaseSource,
    CaseStatus,
    Notification,
    NotificationKind,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
)


def _recharge(db, sub, target):
    req = RechargeRequest(amount=Decimal("100"), channel=TxnChannel.bkash, target_msisdn=target)
    aid = uuid.uuid4()
    payload = req.model_dump(mode="json")
    code = otp.issue(db, subscriber_id=sub.id, action_id=aid, purpose="recharge", payload=payload)
    otp.verify(
        db, subscriber_id=sub.id, action_id=aid, purpose="recharge", payload=payload, code=code
    )
    recharge.execute_recharge(db, sub.id, req, action_id=aid, actor=Actor.agent)


def test_audit_trail_has_no_full_msisdn(db, bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("10"))
    _recharge(db, sub, None)
    audit.record(  # a legacy row that stored the raw number
        db,
        actor=Actor.agent,
        action="recharge",
        subscriber_id=sub.id,
        detail={"target": sub.msisdn, "amount": "100"},
    )
    db.commit()
    trail = monitor.audit_trail(db, limit=20)
    mine = [r for r in trail if r["subscriber_name"] == sub.full_name]
    assert len(mine) >= 2
    assert all(sub.msisdn not in r["detail"] for r in mine)
    assert any(f"target: {sub.msisdn[:3]}" in r["detail"] for r in mine)


def test_no_admin_get_leaks_full_msisdn(api, db, bss_world):
    sub = bss_world.subscriber(full_name="PYTEST Leak", main_balance=Decimal("10"))
    _recharge(db, sub, None)
    db.add(
        Transaction(
            ref=f"TXN-PT{uuid.uuid4().hex[:8]}",
            subscriber_id=sub.id,
            type=TxnType.recharge,
            channel=TxnChannel.bkash,
            amount=Decimal("5"),
            status=TxnStatus.success,
            target_msisdn=sub.msisdn,
        )
    )
    cases.create_case(
        db,
        sub.id,
        category="billing",
        description="PYTEST",
        source=CaseSource.agent,
        action_id=uuid.uuid4(),
    )
    db.commit()
    paths = []
    for route in routes_admin.router.routes:
        if "GET" not in getattr(route, "methods", ()):
            continue
        path = route.path
        for name in route.param_convertors:
            path = path.replace("{" + name + "}", str(sub.id))
        paths.append(path)
    assert any("/subscribers/" in p for p in paths)
    checked = 0
    for path in paths:
        r = api.get(path)
        if r.status_code == 200:
            checked += 1
            assert sub.msisdn not in r.text, path
    assert checked >= 8


@pytest.mark.parametrize(
    "status,words",
    [("open", "open again"), ("in_review", "being reviewed"), ("resolved", "resolved")],
)
def test_case_update_body_uses_words(db, bss_world, status, words):
    sub = bss_world.subscriber()
    row = Notification(
        subscriber_id=sub.id,
        kind=NotificationKind.case_update,
        subject_key="x",
        payload={"case_ref": "TC-2048", "status": status},
    )
    _, body = notifications.describe(row)
    assert body == f"TC-2048 is {words}."


def test_snapshot_case_update_uses_words():
    from app.agent.snapshot import _case_update

    text = _case_update({"case_ref": "TC-2048", "status": "in_review"})
    assert "in_review" not in text and "being reviewed" in text


def test_future_outage_not_degraded_but_started_is(api, bss_world):
    now = datetime.now(timezone.utc)
    bss_world.incident(
        district="PYTEST Soon",
        starts_at=now + timedelta(hours=5),
        ends_at=now + timedelta(hours=9),
    )
    bss_world.incident(district="PYTEST Now")
    health = {d["district"]: d["health"] for d in api.get("/api/admin/network").json()["districts"]}
    assert health["PYTEST Soon"] == "normal"
    assert health["PYTEST Now"] == "degraded"


def test_overview_active_count_uses_network_rule(db, bss_world):
    now = datetime.now(timezone.utc)
    before = ops.overview(db, now=now)["health"]["active_incidents"]
    # starts within 24h: network.is_active counts it, so the control center must too
    inc = bss_world.incident(
        district="PYTEST Cnt",
        starts_at=now + timedelta(hours=5),
        ends_at=now + timedelta(hours=9),
    )
    assert network.is_active(inc, now)
    assert ops.overview(db, now=now)["health"]["active_incidents"] == before + 1
    live = [i for i in ops.network_overview(db, now=now)["incidents"] if i.active]
    assert ops.overview(db, now=now)["health"]["active_incidents"] == len(live)


def test_district_case_normalised(api, bss_world):
    bss_world.subscriber(district="PYTESTburg")

    def post(district):
        return api.post(
            "/api/admin/network/incidents",
            json={
                "district": district,
                "area": "A",
                "kind": "outage",
                "status": "investigating",
                "message": "m",
            },
        )

    assert post("  pytestburg ").json()["district"] == "PYTESTburg"
    assert post("pytest new town").json()["district"] == "Pytest New Town"
    assert post("PYTEST NEW TOWN").json()["district"] == "Pytest New Town"


def test_open_only_includes_in_review(api, db, bss_world):
    sub = bss_world.subscriber()

    def mk():
        return cases.create_case(
            db,
            sub.id,
            category="billing",
            description="PYTEST",
            source=CaseSource.agent,
            action_id=uuid.uuid4(),
        )

    a, b, c = mk(), mk(), mk()
    cases.set_case_status(db, b.ref, CaseStatus.in_review)
    cases.set_case_status(db, c.ref, CaseStatus.resolved)
    refs = {i["ref"] for i in api.get("/api/admin/cases?open_only=true&limit=100").json()["items"]}
    assert {a.ref, b.ref} <= refs and c.ref not in refs


def test_admin_detail_shows_points_spent(api, db, bss_world):
    sub = bss_world.subscriber()
    pkg = bss_world.package()
    offer = bss_world.offer(points_cost=250, package_id=pkg.id)
    db.add(
        Transaction(
            ref=f"TXN-PT{uuid.uuid4().hex[:8]}",
            subscriber_id=sub.id,
            type=TxnType.redeem,
            channel=TxnChannel.balance,
            amount=Decimal("0"),
            offer_id=offer.id,
            package_id=pkg.id,
            status=TxnStatus.success,
        )
    )
    db.commit()
    txns = api.get(f"/api/admin/subscribers/{sub.id}").json()["transactions"]
    assert [t["points_spent"] for t in txns] == [250]


@pytest.mark.parametrize(
    "fields",
    [
        {"points_cost": 0},
        {"points_cost": 1_000_001},
        {"cashback_percent": 0, "min_recharge": 10},
        {"cashback_percent": 101, "min_recharge": 10},
        {"cashback_percent": 5, "min_recharge": 10**11},
        {"cashback_percent": 5, "min_recharge": 10, "cashback_cap": -1},
        {"cashback_percent": 5, "min_recharge": 10, "cashback_cap": 10**11},
    ],
)
def test_offer_bounds_422(api, bss_world, fields):
    pkg = bss_world.package()
    body = {"title": "PYTEST bounds", **fields}
    if "points_cost" in fields:
        body["package_id"] = str(pkg.id)
    assert api.post("/api/admin/offers", json=body).status_code == 422


def test_offer_patch_bounds_422(api):
    made = api.post(
        "/api/admin/offers", json={"title": "PYTEST p", "cashback_percent": 5, "min_recharge": 10}
    ).json()
    r = api.patch(f"/api/admin/offers/{made['id']}", json={"min_recharge": 10**12})
    assert r.status_code == 422
