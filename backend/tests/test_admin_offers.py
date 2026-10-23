"""Admin offers API: kinds, validation, specific audience, delete guard."""

import uuid
from decimal import Decimal

from sqlalchemy import select

from app.bss import rewards
from app.models.telco import AuditEvent, Transaction, TxnChannel, TxnStatus, TxnType

URL = "/api/admin/offers"


def _body(**o):
    return {"title": f"PYTEST {uuid.uuid4().hex[:6]}", **o}


def test_create_each_kind(api, bss_world):
    pkg = bss_world.package()
    pts = api.post(URL, json=_body(points_cost=100, package_id=str(pkg.id)))
    cash = api.post(URL, json=_body(cashback_percent=5, min_recharge=100, cashback_cap=50))
    pack = api.post(URL, json=_body(package_id=str(pkg.id)))
    assert [r.status_code for r in (pts, cash, pack)] == [201, 201, 201]
    assert pts.json()["kind"] == "points" and pts.json()["package_name"] == pkg.name
    assert cash.json()["kind"] == "cashback" and cash.json()["cashback_percent"] == 5
    assert pack.json()["kind"] == "pack" and pack.json()["redemptions"] == 0
    listed = {o["id"] for o in api.get(URL).json()}
    assert {pts.json()["id"], cash.json()["id"], pack.json()["id"]} <= listed
    assert api.get("/api/admin/packages").json()


def test_rejects_mixed_or_empty_kind(api, bss_world):
    pkg = bss_world.package()
    bad = [
        _body(points_cost=10, package_id=str(pkg.id), cashback_percent=5, min_recharge=10),
        _body(),
        _body(points_cost=0, package_id=str(pkg.id)),
        _body(points_cost=10),
        _body(cashback_percent=0, min_recharge=10),
        _body(cashback_percent=101, min_recharge=10),
        _body(cashback_percent=5),
        _body(package_id=str(pkg.id), starts_on="2026-02-01", ends_on="2026-01-01"),
        _body(package_id=str(uuid.uuid4())),
    ]
    assert [api.post(URL, json=b).status_code for b in bad] == [422] * len(bad)


def test_specific_audience_eligibility(api, db, bss_world):
    a, b = bss_world.subscriber(), bss_world.subscriber()
    pkg = bss_world.package()
    r = api.post(
        URL,
        json=_body(package_id=str(pkg.id), audience="specific", subscriber_ids=[str(a.id)]),
    )
    assert r.status_code == 201
    assert r.json()["subscribers"][0]["msisdn_masked"] == f"{a.msisdn[:3]}••••{a.msisdn[-4:]}"
    oid = uuid.UUID(r.json()["id"])
    assert oid in {o.id for o in rewards.get_offers_and_points(db, a.id).offers}
    assert oid not in {o.id for o in rewards.get_offers_and_points(db, b.id).offers}


def test_specific_needs_subscribers(api, bss_world):
    pkg = bss_world.package()
    for ids in ([], [str(uuid.uuid4())]):
        r = api.post(
            URL, json=_body(package_id=str(pkg.id), audience="specific", subscriber_ids=ids)
        )
        assert r.status_code == 422
    r = api.post(URL, json=_body(package_id=str(pkg.id), audience="prepaid", subscriber_ids=[]))
    assert r.status_code == 201 and r.json()["subscriber_ids"] == []


def test_patch_revalidates(api, bss_world):
    pkg = bss_world.package()
    oid = api.post(URL, json=_body(package_id=str(pkg.id))).json()["id"]
    assert api.patch(f"{URL}/{oid}", json={"cashback_percent": 5}).status_code == 422
    r = api.patch(f"{URL}/{oid}", json={"is_active": False, "title": "PYTEST renamed"})
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert r.json()["title"] == "PYTEST renamed" and r.json()["kind"] == "pack"
    r = api.patch(
        f"{URL}/{oid}",
        json={"package_id": None, "cashback_percent": 10, "min_recharge": 50},
    )
    assert r.json()["kind"] == "cashback"
    assert api.patch(f"{URL}/{oid}", json={"audience": "specific"}).status_code == 422
    assert api.patch(f"{URL}/{uuid.uuid4()}", json={"is_active": True}).status_code == 404


def test_delete_offer_in_use_409(api, db, bss_world):
    pkg = bss_world.package()
    sub = bss_world.subscriber()
    used = api.post(URL, json=_body(package_id=str(pkg.id))).json()["id"]
    free = api.post(URL, json=_body(package_id=str(pkg.id))).json()["id"]
    db.add(
        Transaction(
            ref=f"TXN-PT{uuid.uuid4().hex[:8]}",
            subscriber_id=sub.id,
            type=TxnType.redeem,
            channel=TxnChannel.balance,
            amount=Decimal("0"),
            offer_id=uuid.UUID(used),
            status=TxnStatus.success,
        )
    )
    db.commit()
    r = api.delete(f"{URL}/{used}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "offer_in_use"
    assert api.delete(f"{URL}/{free}").status_code == 204
    assert api.delete(f"{URL}/{free}").status_code == 404
    actions = set(db.scalars(select(AuditEvent.action).where(AuditEvent.action.like("offer_%"))))
    assert {"offer_create", "offer_delete"} <= actions
