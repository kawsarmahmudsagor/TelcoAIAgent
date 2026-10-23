from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, select

from app.bss import otp, recharge, rewards, transactions
from app.bss.types import RechargeRequest
from app.models.telco import (
    Actor,
    AuditEvent,
    CaseSource,
    CaseStatus,
    Subscriber,
    SupportCase,
    TxnChannel,
)

START = "/api/me/actions/start"
RECHARGE = {"kind": "recharge", "amount": 100, "channel": "bkash"}
COUNT_KEYS = {"pack_expiring", "low_balance", "low_data"}


def _audits(db, action, **where):
    db.rollback()
    q = select(AuditEvent).where(AuditEvent.action == action)
    for k, v in where.items():
        q = q.where(getattr(AuditEvent, k) == v)
    return list(db.scalars(q))


def test_run_nudges_endpoint(api, bss_world, db):
    r = api.post("/api/admin/nudges/run")
    assert r.status_code == 200, r.text
    assert set(r.json()["created"]) == COUNT_KEYS
    again = api.post("/api/admin/nudges/run")
    assert again.json()["created"] == {k: 0 for k in COUNT_KEYS}
    assert len(_audits(db, "nudges_run", subscriber_id=None, actor=Actor.admin)) >= 2


def test_nudges_run_requires_admin(anon_api):
    assert anon_api.post("/api/admin/nudges/run").status_code == 401


def test_portal_throttle_sixth_code_429(bss_world, customer_api):
    sub = bss_world.subscriber(main_balance=Decimal("500"))
    c = customer_api(sub.id)
    for _ in range(5):
        assert c.post(START, json=RECHARGE).status_code == 200
    r = c.post(START, json=RECHARGE)
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "too_many_codes"


def test_otp_issue_and_verify_are_audited_without_code(db, bss_world):
    sub = bss_world.subscriber()
    aid, payload = uuid4(), {"x": 1}
    code = otp.issue(
        db, subscriber_id=sub.id, action_id=aid, purpose="purchase", payload=payload,
        actor=Actor.portal,
    )
    otp.verify(
        db, subscriber_id=sub.id, action_id=aid, purpose="purchase", payload=payload, code=code,
        actor=Actor.portal,
    )
    issued = _audits(db, "otp_issue", subscriber_id=sub.id)
    verified = _audits(db, "otp_verify", subscriber_id=sub.id)
    assert len(issued) == 1 and len(verified) == 1
    assert issued[0].detail == {"purpose": "purchase", "ok": True}
    assert verified[0].detail == {"purpose": "purchase", "ok": True}
    assert code not in str(issued[0].detail) + str(verified[0].detail)


def test_target_credit_audit(db, bss_world):
    a = bss_world.subscriber(main_balance=Decimal("500"))
    b = bss_world.subscriber()
    req = RechargeRequest(
        amount=Decimal("100"), channel=TxnChannel.bkash, target_msisdn=b.msisdn
    )
    aid, payload = uuid4(), req.model_dump(mode="json")
    code = otp.issue(db, subscriber_id=a.id, action_id=aid, purpose="recharge", payload=payload)
    otp.verify(
        db, subscriber_id=a.id, action_id=aid, purpose="recharge", payload=payload, code=code
    )
    res = recharge.execute_recharge(db, a.id, req, action_id=aid, actor=Actor.agent)
    rows = _audits(db, "target_credit", subscriber_id=b.id)
    assert len(rows) == 1
    d = rows[0].detail
    assert d["ref"] == res.transaction_ref and d["amount"] == "100.00"
    assert a.msisdn not in d["from_masked"] and d["from_masked"]
    assert len(_audits(db, "recharge", subscriber_id=a.id)) == 1


def test_redeem_transaction_has_points_spent(db, bss_world):
    sub = bss_world.subscriber(reward_points=500)
    offer = bss_world.offer(title="PYTEST redeem", points_cost=120)
    aid, payload = uuid4(), {"offer_id": str(offer.id)}
    code = otp.issue(db, subscriber_id=sub.id, action_id=aid, purpose="redeem", payload=payload)
    otp.verify(
        db, subscriber_id=sub.id, action_id=aid, purpose="redeem", payload=payload, code=code
    )
    rewards.execute_redeem(db, sub.id, offer.id, action_id=aid, actor=Actor.agent)
    [view] = transactions.lookup(db, sub.id)
    assert view.points_spent == 120


def test_me_cases_newest_first_across_statuses(bss_world, customer_api, db):
    sub = bss_world.subscriber()
    now = datetime.now(timezone.utc)
    for i in range(21):
        db.add(
            SupportCase(
                ref=f"TC-9{i:05d}", subscriber_id=sub.id, category="PYTEST", description="old", source=CaseSource.portal,
                created_at=now - timedelta(days=30, minutes=i),
            )
        )
    db.commit()
    new = SupportCase(
        ref="TC-999999", subscriber_id=sub.id, category="PYTEST", description="new",
        source=CaseSource.portal, status=CaseStatus.resolved, created_at=now,
    )
    db.add(new)
    db.commit()
    rows = customer_api(sub.id).get("/api/me/cases").json()
    assert len(rows) == 20 and rows[0]["ref"] == "TC-999999"


def test_deleting_subscriber_keeps_audit_rows(db, bss_world):
    sub = bss_world.subscriber()
    otp.issue(db, subscriber_id=sub.id, action_id=uuid4(), purpose="purchase", payload={})
    sid = sub.id
    row_id = _audits(db, "otp_issue", subscriber_id=sid)[0].id
    db.execute(delete(Subscriber).where(Subscriber.id == sid))
    db.commit()
    db.expire_all()
    kept = db.get(AuditEvent, row_id)
    assert kept is not None and kept.subscriber_id is None
    db.delete(kept)
    db.commit()
