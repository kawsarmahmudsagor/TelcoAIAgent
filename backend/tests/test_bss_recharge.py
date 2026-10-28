from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.bss import otp, recharge, transactions
from app.bss.errors import InvalidMsisdn, InvalidRequest, LimitExceeded, OtpInvalid
from app.bss.types import RechargeRequest
from app.models.telco import (
    Actor,
    AuditEvent,
    Balance,
    OfferAudience,
    PlanType,
    Subscriber,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
)


def _req(amount, target=None, channel=TxnChannel.bkash):
    return RechargeRequest(amount=Decimal(str(amount)), channel=channel, target_msisdn=target)


def _confirm(db, sub, req):
    aid = uuid4()
    payload = req.model_dump(mode="json")
    code = otp.issue(db, subscriber_id=sub.id, action_id=aid, purpose="recharge", payload=payload)
    otp.verify(
        db, subscriber_id=sub.id, action_id=aid, purpose="recharge", payload=payload, code=code
    )
    return aid


def _do(db, sub, req):
    return recharge.execute_recharge(
        db, sub.id, req, action_id=_confirm(db, sub, req), actor=Actor.agent
    )


def test_recharge_limits_inclusive(bss_world, db):
    s = bss_world.subscriber()
    for ok in ("20", "1000"):
        recharge.preview_recharge(db, s.id, _req(ok))
    for bad in ("19.99", "1000.01"):
        with pytest.raises(LimitExceeded):
            recharge.preview_recharge(db, s.id, _req(bad))


def test_recharge_rejects_non_payment_channel(bss_world, db):
    s = bss_world.subscriber()
    with pytest.raises(InvalidRequest):
        recharge.preview_recharge(db, s.id, _req(100, channel=TxnChannel.balance))


def test_daily_cap_5000(bss_world, db):
    s = bss_world.subscriber()
    for _ in range(5):
        _do(db, s, _req(1000))
    with pytest.raises(LimitExceeded):
        recharge.preview_recharge(db, s.id, _req(20))


def test_msisdn_normalisation_and_validation(bss_world, db):
    s = bss_world.subscriber()
    q = recharge.preview_recharge(db, s.id, _req(100, "+8801712-342841"))
    assert q.target_msisdn == "01712342841"
    assert q.is_own_number is False
    assert recharge.preview_recharge(db, s.id, _req(100, "880 1712342841")).target_msisdn == (
        "01712342841"
    )
    # The model writes Bangla replies, digits included.
    assert recharge.preview_recharge(db, s.id, _req(100, "০১৭১২৩৪২৮৪১")).target_msisdn == (
        "01712342841"
    )
    with pytest.raises(InvalidMsisdn):
        recharge.preview_recharge(db, s.id, _req(100, "0121234567"))


def test_execute_recharge_credits_own_prepaid_with_cashback(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("10"))
    # 100% capped at 30 beats any realistic seeded offer at this amount.
    bss_world.offer(cashback_percent=Decimal("100"), cashback_cap=Decimal("30"))
    req = _req(100)
    assert recharge.preview_recharge(db, s.id, req).cashback == Decimal("30.00")
    out = _do(db, s, req)
    assert out.cashback == Decimal("30.00")
    assert out.main_balance == Decimal("140")
    txn = db.scalars(select(Transaction).where(Transaction.subscriber_id == s.id)).one()
    assert (txn.type, txn.status, txn.cashback) == (
        TxnType.recharge,
        TxnStatus.success,
        Decimal("30.00"),
    )
    n = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.subscriber_id == s.id, AuditEvent.action == "recharge")
    )
    assert n == 1


def test_cashback_respects_min_recharge_audience_and_dates(bss_world, db):
    s = bss_world.subscriber()
    today = datetime.now(timezone.utc).date()
    kw = dict(cashback_percent=Decimal("100"), cashback_cap=Decimal("500"))
    baseline = recharge.preview_recharge(db, s.id, _req(100)).cashback
    bss_world.offer(min_recharge=Decimal("900"), **kw)
    bss_world.offer(audience=OfferAudience.postpaid, **kw)
    bss_world.offer(is_active=False, **kw)
    bss_world.offer(starts_on=today + timedelta(days=2), **kw)
    bss_world.offer(ends_on=today - timedelta(days=2), **kw)
    # None of the PYTEST offers apply, so cashback is unchanged from the baseline.
    assert recharge.preview_recharge(db, s.id, _req(100)).cashback == baseline
    bss_world.offer(min_recharge=Decimal("100"), audience=OfferAudience.prepaid, **kw)
    assert recharge.preview_recharge(db, s.id, _req(100)).cashback == Decimal("100.00")


def test_recharge_other_unknown_number(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("50"))
    bss_world.offer(cashback_percent=Decimal("100"), cashback_cap=Decimal("30"))
    out = _do(db, s, _req(100, "01812345678"))
    assert out.cashback == Decimal("0")
    assert out.main_balance == Decimal("50")
    txn = db.scalars(select(Transaction).where(Transaction.subscriber_id == s.id)).one()
    assert (txn.status, txn.target_msisdn) == (TxnStatus.success, "01812345678")


def test_recharge_other_known_prepaid_credits_them_without_cashback(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("50"))
    t = bss_world.subscriber(main_balance=Decimal("5"))
    bss_world.offer(cashback_percent=Decimal("100"), cashback_cap=Decimal("30"))
    out = _do(db, s, _req(100, t.msisdn))
    assert out.cashback == Decimal("0")
    assert out.main_balance == Decimal("50")
    db.expire_all()
    assert db.get(Balance, t.id).main_balance == Decimal("105")


def test_recharge_postpaid_reduces_due(bss_world, db):
    s = bss_world.subscriber(plan_type=PlanType.postpaid, postpaid_due=Decimal("150"))
    out = _do(db, s, _req(100))
    assert out.postpaid_due == Decimal("50")
    out = _do(db, s, _req(100))
    assert out.postpaid_due == Decimal("0")
    assert out.main_balance == Decimal("0")


def test_execute_recharge_requires_verified_otp(bss_world, db):
    s = bss_world.subscriber()
    with pytest.raises(OtpInvalid):
        recharge.execute_recharge(db, s.id, _req(100), action_id=uuid4(), actor=Actor.agent)


def test_execute_recharge_same_action_twice_is_noop(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("0"))
    req = _req(100)
    aid = _confirm(db, s, req)
    first = recharge.execute_recharge(db, s.id, req, action_id=aid, actor=Actor.agent)
    second = recharge.execute_recharge(db, s.id, req, action_id=aid, actor=Actor.agent)
    assert second.transaction_ref == first.transaction_ref
    assert second.main_balance == first.main_balance
    count = db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.subscriber_id == s.id)
    )
    assert count == 1


def test_recharge_replay_from_other_subscriber_rejected(bss_world, db):
    a = bss_world.subscriber(main_balance=Decimal("0"))
    b = bss_world.subscriber(main_balance=Decimal("0"))
    req = _req(100)
    aid = _confirm(db, a, req)
    recharge.execute_recharge(db, a.id, req, action_id=aid, actor=Actor.agent)
    with pytest.raises(OtpInvalid):
        recharge.execute_recharge(db, b.id, req, action_id=aid, actor=Actor.agent)
    db.expire_all()
    assert db.get(Balance, b.id).main_balance == Decimal("0")


def test_lookup_scoped_to_subscriber_and_ref(bss_world, db):
    a = bss_world.subscriber()
    b = bss_world.subscriber()
    out_a = _do(db, a, _req(100))
    out_b = _do(db, b, _req(50))
    rows = transactions.lookup(db, a.id)
    assert [r.ref for r in rows] == [out_a.transaction_ref]
    assert rows[0].package_name is None
    assert transactions.lookup(db, a.id, ref=out_b.transaction_ref.lower()) == []
    found = transactions.lookup(db, a.id, ref=out_a.transaction_ref.lower())
    assert found[0].amount == Decimal("100")
    assert transactions.lookup(db, a.id, status=TxnStatus.failed) == []
    assert transactions.lookup(db, a.id, type=TxnType.purchase) == []


def test_lookup_days_window_and_ref_ignores_it(bss_world, db):
    a = bss_world.subscriber()
    out = _do(db, a, _req(100))
    later = datetime.now(timezone.utc) + timedelta(days=40)
    assert transactions.lookup(db, a.id, now=later) == []
    assert len(transactions.lookup(db, a.id, ref=out.transaction_ref, now=later)) == 1
    assert len(transactions.lookup(db, a.id, days=60, now=later)) == 1


def test_postpaid_own_recharge_gets_no_cashback(bss_world, db):
    s = bss_world.subscriber(plan_type=PlanType.postpaid, postpaid_due=Decimal("150"))
    bss_world.offer(
        audience=OfferAudience.all,
        cashback_percent=Decimal("100"),
        cashback_cap=Decimal("30"),
        min_recharge=Decimal("50"),
    )
    req = _req(100)
    assert recharge.preview_recharge(db, s.id, req).cashback == Decimal("0")
    out = _do(db, s, req)
    assert out.cashback == Decimal("0")
    assert out.postpaid_due == Decimal("50")
    txn = db.scalars(select(Transaction).where(Transaction.subscriber_id == s.id)).one()
    assert txn.cashback == Decimal("0")


def test_recharge_crossing_known_subscribers_both_credited(bss_world, db):
    a = bss_world.subscriber(main_balance=Decimal("0"))
    b = bss_world.subscriber(main_balance=Decimal("0"))
    _do(db, a, _req(100, b.msisdn))
    _do(db, b, _req(50, a.msisdn))
    db.expire_all()
    assert db.get(Balance, a.id).main_balance == Decimal("50")
    assert db.get(Balance, b.id).main_balance == Decimal("100")


def test_recharge_concurrent_confirm_replays_after_lock(bss_world, db, monkeypatch):
    from app.bss import _txn
    from app.db.session import SessionLocal
    from app.models.telco import AuditEvent

    # Postpaid: no cashback offers apply, so the arithmetic is exact.
    s = bss_world.subscriber(plan_type=PlanType.postpaid, postpaid_due=Decimal("6000"))
    for _ in range(4):
        _do(db, s, _req(1000))
    req = _req(1000)  # brings the day to exactly the 5000 cap
    aid = _confirm(db, s, req)
    first = recharge.execute_recharge(db, s.id, req, action_id=aid, actor=Actor.agent)
    real, calls = _txn.existing, {"n": 0}

    def stale_first(*args, **kwargs):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(*args, **kwargs)

    monkeypatch.setattr(_txn, "existing", stale_first)
    other = SessionLocal()
    try:
        second = recharge.execute_recharge(other, s.id, req, action_id=aid, actor=Actor.portal)
    finally:
        other.rollback()
        other.close()
    assert second.transaction_ref == first.transaction_ref
    assert second.postpaid_due == first.postpaid_due == Decimal("1000")
    db.expire_all()
    assert db.get(Balance, s.id).postpaid_due == Decimal("1000")
    for model in (Transaction, AuditEvent):
        q = select(func.count()).select_from(model).where(model.subscriber_id == s.id)
        if model is AuditEvent:  # the OTP trail is audited too; count the writes only
            q = q.where(AuditEvent.action.not_in(("otp_issue", "otp_verify")))
        n = db.scalar(q)
        assert n == 5, model.__name__


def test_recharge_replay_ignores_other_txn_type_with_same_action(bss_world, db):
    from app.bss import packages
    from app.bss.types import PurchaseRequest

    s = bss_world.subscriber(main_balance=Decimal("500"))
    p = bss_world.package(price=Decimal("69"))
    preq = PurchaseRequest(package_code=p.code, pay_from=TxnChannel.balance)
    payload = preq.model_dump(mode="json")
    aid = uuid4()
    code = otp.issue(db, subscriber_id=s.id, action_id=aid, purpose="purchase", payload=payload)
    otp.verify(
        db, subscriber_id=s.id, action_id=aid, purpose="purchase", payload=payload, code=code
    )
    packages.execute_purchase(db, s.id, preq, action_id=aid, actor=Actor.agent)
    with pytest.raises(OtpInvalid):
        recharge.execute_recharge(db, s.id, _req(100), action_id=aid, actor=Actor.agent)


def test_recharge_amount_quantized_to_two_places():
    a = RechargeRequest(amount=Decimal("100"), channel=TxnChannel.bkash)
    b = RechargeRequest(amount=Decimal("100.00"), channel=TxnChannel.bkash)
    assert a.amount == b.amount and str(a.amount) == "100.00"
    assert otp.request_hash("recharge", a.model_dump(mode="json")) == otp.request_hash(
        "recharge", b.model_dump(mode="json")
    )
    assert str(RechargeRequest(amount="99.995", channel=TxnChannel.bkash).amount) == "100.00"
    assert str(RechargeRequest(amount="99.994", channel=TxnChannel.bkash).amount) == "99.99"


def test_recharge_confirmed_as_100_executes_as_100_00(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("0"))
    aid = _confirm(db, s, _req("100"))
    out = recharge.execute_recharge(db, s.id, _req("100.00"), action_id=aid, actor=Actor.agent)
    assert out.amount == Decimal("100.00") and str(out.amount) == "100.00"
    assert out.main_balance == Decimal("100") + out.cashback


@pytest.mark.parametrize(
    ("amount", "points"),
    [("20", 2), ("29.99", 2), ("45", 4), ("45.50", 4), ("50", 5), ("99.99", 9), ("1000", 100)],
)
def test_points_for_counts_full_ten_taka_only(amount, points):
    assert recharge.points_for(Decimal(amount)) == points


def test_recharge_earns_points_for_payer(bss_world, db):
    s = bss_world.subscriber(reward_points=10)
    t = bss_world.subscriber(reward_points=0)
    assert recharge.preview_recharge(db, s.id, _req(45)).points_earned == 4
    out = _do(db, s, _req(45))
    assert (out.points_earned, out.reward_points) == (4, 14)
    # Recharging someone else still earns the payer, never the target.
    out = _do(db, s, _req("99.99", t.msisdn))
    assert (out.points_earned, out.reward_points) == (9, 23)
    db.expire_all()
    assert db.get(Subscriber, t.id).reward_points == 0
    txns = db.scalars(
        select(Transaction).where(Transaction.subscriber_id == s.id).order_by(Transaction.ref)
    ).all()
    assert [x.points_earned for x in txns] == [4, 9]
    assert sorted(v.points_earned for v in transactions.lookup(db, s.id)) == [4, 9]


def test_recharge_points_not_doubled_on_replay(bss_world, db):
    s = bss_world.subscriber(plan_type=PlanType.postpaid, postpaid_due=Decimal("500"))
    req = _req(120)
    aid = _confirm(db, s, req)
    first = recharge.execute_recharge(db, s.id, req, action_id=aid, actor=Actor.agent)
    again = recharge.execute_recharge(db, s.id, req, action_id=aid, actor=Actor.agent)
    assert first.points_earned == again.points_earned == 12
    assert first.reward_points == again.reward_points == 12
