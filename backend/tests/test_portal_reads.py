import uuid
from decimal import Decimal

import pytest

from app.models.telco import Transaction, TxnChannel, TxnStatus, TxnType

GET_PATHS = [
    "/api/me",
    "/api/me/summary",
    "/api/me/usage",
    "/api/me/transactions",
    "/api/me/packages",
    "/api/me/recommendations",
    "/api/me/offers",
    "/api/me/cases",
    "/api/me/network",
]


def _txn(db, sub, ref):
    db.add(
        Transaction(
            ref=ref,
            subscriber_id=sub.id,
            type=TxnType.recharge,
            channel=TxnChannel.bkash,
            amount=Decimal("50"),
            status=TxnStatus.success,
        )
    )
    db.commit()


def test_summary_is_own_subscriber(bss_world, customer_api):
    a, b = bss_world.subscriber(), bss_world.subscriber()
    r = customer_api(a.id).get("/api/me/summary")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["subscriber_id"] == str(a.id)
    assert customer_api(b.id).get("/api/me/summary").json()["subscriber_id"] == str(b.id)


def test_money_is_json_number(bss_world, customer_api):
    a = bss_world.subscriber(main_balance=Decimal("486.50"))
    summary = customer_api(a.id).get("/api/me/summary").json()
    assert isinstance(summary["main_balance"], (int, float))
    assert summary["main_balance"] == 486.5


def test_usage_period_bounds(bss_world, customer_api):
    c = customer_api(bss_world.subscriber().id)
    assert c.get("/api/me/usage?period_days=0").status_code == 422
    assert c.get("/api/me/usage?period_days=91").status_code == 422
    r = c.get("/api/me/usage?period_days=7")
    assert r.status_code == 200
    assert r.json()["period_days"] == 7


def test_transactions_only_own(db, bss_world, customer_api):
    a, b = bss_world.subscriber(), bss_world.subscriber()
    ref_a, ref_b = f"PT{uuid.uuid4().hex[:10]}", f"PT{uuid.uuid4().hex[:10]}"
    _txn(db, a, ref_a)
    _txn(db, b, ref_b)
    rows = customer_api(a.id).get("/api/me/transactions").json()
    refs = [t["ref"] for t in rows]
    assert ref_a in refs and ref_b not in refs
    assert isinstance(rows[0]["amount"], (int, float))
    assert customer_api(a.id).get("/api/me/transactions?limit=51").status_code == 422
    assert customer_api(a.id).get("/api/me/transactions?days=91").status_code == 422


def test_create_case_idempotent_on_request_id(bss_world, customer_api):
    c = customer_api(bss_world.subscriber().id)
    body = {
        "category": "billing",
        "description": "I was charged twice for one pack",
        "request_id": str(uuid.uuid4()),
    }
    r1, r2 = c.post("/api/me/cases", json=body), c.post("/api/me/cases", json=body)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["ref"] == r2.json()["ref"]
    cases = c.get("/api/me/cases").json()
    assert len(cases) == 1
    assert cases[0]["source"] == "portal"


@pytest.mark.parametrize(
    "patch",
    [{"category": "nonsense"}, {"description": "too short"}, {"description": " " * 20 + "abc "}],
)
def test_create_case_rejects_unknown_category_and_short_text(bss_world, customer_api, patch):
    body = {
        "category": "billing",
        "description": "A long enough description",
        "request_id": str(uuid.uuid4()),
        **patch,
    }
    c = customer_api(bss_world.subscriber().id)
    assert c.post("/api/me/cases", json=body).status_code == 422


def test_network_defaults_to_own_district(bss_world, customer_api):
    bss_world.incident(district="Sylhet", area="PYTEST Sylhet")
    bss_world.incident(district="Dhaka", area="PYTEST Dhaka")
    sub = bss_world.subscriber(district="Sylhet")
    rows = customer_api(sub.id).get("/api/me/network").json()
    areas = [i["area"] for i in rows]
    assert "PYTEST Sylhet" in areas and "PYTEST Dhaka" not in areas


@pytest.mark.parametrize("path", GET_PATHS)
def test_me_routes_need_customer(anon_api, path):
    assert anon_api.get(path).status_code == 401
