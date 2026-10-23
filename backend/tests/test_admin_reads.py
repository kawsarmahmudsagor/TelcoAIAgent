import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete

from app.api import routes_admin
from app.models.telco import (
    CasePriority,
    CaseSource,
    CaseStatus,
    SupportCase,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
)


def _admin_get_paths() -> list[str]:
    paths = []
    for route in routes_admin.router.routes:
        if "GET" in getattr(route, "methods", ()):
            path = route.path
            for name in route.param_convertors:
                path = path.replace("{" + name + "}", str(uuid.uuid4()))
            paths.append(path)
    return paths


@pytest.mark.parametrize("path", _admin_get_paths())
def test_admin_routes_refuse_customer_and_anon(path, customer_api, anon_api, bss_world):
    assert anon_api.get(path).status_code == 401
    sub = bss_world.subscriber()
    assert customer_api(sub.id).get(path).status_code == 401


def test_admin_route_list_not_empty():
    assert len(_admin_get_paths()) >= 6


@pytest.fixture
def txns(db):
    made = []

    def make(sub, status=TxnStatus.success, amount="100", type=TxnType.recharge):
        t = Transaction(
            ref=f"TXN-PT{uuid.uuid4().hex[:8]}",
            subscriber_id=sub.id,
            type=type,
            channel=TxnChannel.bkash,
            amount=Decimal(amount),
            status=status,
            target_msisdn=sub.msisdn,
        )
        db.add(t)
        db.commit()
        made.append(t.id)
        return t

    yield make
    db.rollback()
    db.execute(delete(Transaction).where(Transaction.id.in_(made)))
    db.commit()


def test_overview_counts_today_and_zero_fills(api, bss_world, txns):
    before = api.get("/api/admin/overview").json()
    sub = bss_world.subscriber()
    txns(sub, amount="250")
    r = api.get("/api/admin/overview")
    after = r.json()
    assert r.headers["cache-control"] == "no-store"
    assert len(after["activity"]) == 7
    assert after["recharge_today"]["count"] == before["recharge_today"]["count"] + 1
    assert after["recharge_today"]["amount"] == pytest.approx(
        before["recharge_today"]["amount"] + 250
    )
    assert after["activity"][-1]["recharge_amount"] == pytest.approx(
        before["activity"][-1]["recharge_amount"] + 250
    )
    assert after["subscribers"]["total"] == before["subscribers"]["total"] + 1


def test_subscriber_search_masks_msisdn(api, bss_world):
    sub = bss_world.subscriber(full_name="PYTEST Searchable")
    r = api.get(f"/api/admin/subscribers?q={sub.msisdn[-4:]}&limit=100")
    assert r.status_code == 200
    assert str(sub.id) in [i["id"] for i in r.json()["items"]]
    assert sub.msisdn not in r.text
    by_name = api.get("/api/admin/subscribers?q=pytest searchable").json()
    assert str(sub.id) in [i["id"] for i in by_name["items"]]
    assert api.get("/api/admin/subscribers?limit=101").status_code == 422


def test_subscriber_detail(api, bss_world):
    sub = bss_world.subscriber(main_balance=Decimal("486.50"))
    r = api.get(f"/api/admin/subscribers/{sub.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["subscriber"]["main_balance"] == 486.5
    assert body["summary"]["subscriber_id"] == str(sub.id)
    assert body["transactions"] == [] and body["cases"] == [] and body["notifications"] == []
    assert sub.msisdn not in r.text


def test_subscriber_detail_404(api):
    assert api.get(f"/api/admin/subscribers/{uuid.uuid4()}").status_code == 404


def test_transactions_filters_and_stats(api, bss_world, txns):
    before = api.get("/api/admin/transactions/stats").json()
    sub = bss_world.subscriber()
    txns(sub, TxnStatus.success, "100")
    txns(sub, TxnStatus.success, "50")
    txns(sub, TxnStatus.failed, "70")
    txns(sub, TxnStatus.pending, "20")
    detail = api.get(f"/api/admin/subscribers/{sub.id}")
    assert len(detail.json()["transactions"]) == 4 and sub.msisdn not in detail.text
    r = api.get("/api/admin/transactions?status=pending&limit=100")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items and {i["status"] for i in items} == {"pending"}
    assert sub.msisdn not in r.text
    mine = api.get(f"/api/admin/transactions?q={sub.msisdn[-6:]}").json()
    assert mine["total"] == 4
    assert mine["items"][0]["subscriber_name"] == sub.full_name
    assert api.get("/api/admin/transactions?days=91").status_code == 422

    s = api.get("/api/admin/transactions/stats").json()
    assert s["success"] == before["success"] + 2
    assert s["failed"] == before["failed"] + 1
    assert s["pending"] == before["pending"] + 1
    assert s["volume"] == pytest.approx(before["volume"] + 150)
    assert s["success_rate"] == pytest.approx(s["success"] / (s["success"] + s["failed"]))


def test_attention_lists_pending_transactions(api, bss_world, txns):
    txns(bss_world.subscriber(), TxnStatus.pending)
    attention = api.get("/api/admin/overview").json()["attention"]
    assert any(
        a["href"] == "/dashboard/transactions?status=pending" and a["severity"] == "investigate"
        for a in attention
    )


def test_attention_lists_stale_high_cases_and_outages(api, db, bss_world):
    sub = bss_world.subscriber()
    case = SupportCase(
        ref=f"TC-PT{uuid.uuid4().hex[:6]}",
        subscriber_id=sub.id,
        category="PYTEST",
        description="old",
        priority=CasePriority.high,
        status=CaseStatus.open,
        source=CaseSource.agent,
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    db.add(case)
    db.commit()
    bss_world.incident()
    attention = api.get("/api/admin/overview").json()["attention"]
    hrefs = {a["href"] for a in attention}
    assert "/dashboard/cases?priority=high" in hrefs
    assert "/dashboard/network" in hrefs


def test_ai_monitor_shape(api):
    r = api.get("/api/admin/ai-monitor?window=7d")
    assert r.status_code == 200
    assert set(r.json()) == {"metrics", "review_queue", "audit_trail"}
    assert api.get("/api/admin/ai-monitor?window=1y").status_code == 422
