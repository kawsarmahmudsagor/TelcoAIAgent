import re
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.bss import otp, packages
from app.bss.errors import InsufficientBalance, InvalidRequest, OtpInvalid
from app.bss.types import PurchaseRequest
from app.models.telco import (
    Actor,
    AuditEvent,
    PackageKind,
    PlanType,
    Subscription,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
    UsageKind,
)


def _mine(items):
    return [i for i in items if i.code.startswith("PT-")]


def _req(pkg, pay=TxnChannel.balance):
    return PurchaseRequest(package_code=pkg.code, pay_from=pay)


def _confirm(db, sub, req):
    aid = uuid4()
    payload = req.model_dump(mode="json")
    code = otp.issue(db, subscriber_id=sub.id, action_id=aid, purpose="purchase", payload=payload)
    otp.verify(
        db, subscriber_id=sub.id, action_id=aid, purpose="purchase", payload=payload, code=code
    )
    return aid


def test_search_filters_and_sorts(bss_world, db):
    a = bss_world.package(kind=PackageKind.data, data_mb=5120, price=Decimal("300"), validity_days=7)
    b = bss_world.package(kind=PackageKind.data, data_mb=10240, price=Decimal("200"), validity_days=7)
    c = bss_world.package(kind=PackageKind.voice, minutes=100, price=Decimal("50"), validity_days=30)
    assert [p.code for p in _mine(packages.search(db))] == [c.code, b.code, a.code]
    assert [p.code for p in _mine(packages.search(db, kind=PackageKind.data))] == [b.code, a.code]
    assert [p.code for p in _mine(packages.search(db, max_price=Decimal("200")))] == [c.code, b.code]
    assert [p.code for p in _mine(packages.search(db, min_data_gb=8))] == [b.code]
    assert [p.code for p in _mine(packages.search(db, validity_days=30))] == [c.code]


def test_search_excludes_inactive(bss_world, db):
    bss_world.package(is_active=False)
    assert _mine(packages.search(db)) == []


def test_recommend_bundle_for_data_and_voice_user(bss_world, db):
    s = bss_world.subscriber()
    bss_world.usage(s, UsageKind.data, 4000)
    bss_world.usage(s, UsageKind.voice, 100)
    best = bss_world.package(kind=PackageKind.bundle, data_mb=5000, minutes=200, price=Decimal("300"))
    bss_world.package(kind=PackageKind.bundle, data_mb=1000, minutes=20, price=Decimal("100"))
    bss_world.package(kind=PackageKind.data, data_mb=9000, price=Decimal("50"))
    bss_world.package(kind=PackageKind.bundle, data_mb=6000, minutes=300, price=Decimal("400"))
    bss_world.package(kind=PackageKind.bundle, data_mb=7000, minutes=300, price=Decimal("500"))
    assert len(packages.recommend(db, s.id)) <= 3
    recs = packages.recommend(db, s.id, limit=1000)
    assert all(r.package.kind == PackageKind.bundle for r in recs)
    mine = [r for r in recs if r.package.code.startswith("PT-")]
    assert len(mine) == 4
    assert mine[0].package.code == best.code
    assert "৳300/month" in mine[0].reason


def test_recommend_data_only_user_gets_data_packs(bss_world, db):
    s = bss_world.subscriber()
    bss_world.usage(s, UsageKind.data, 4000)
    bss_world.package(kind=PackageKind.data, data_mb=5000, price=Decimal("100"))
    bss_world.package(kind=PackageKind.bundle, data_mb=5000, minutes=100, price=Decimal("50"))
    recs = packages.recommend(db, s.id, limit=1000)
    assert all(r.package.kind == PackageKind.data for r in recs)
    assert len(_mine([r.package for r in recs])) == 1


def test_preview_insufficient_balance(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("50"))
    p = bss_world.package(price=Decimal("69"))
    with pytest.raises(InsufficientBalance):
        packages.preview_purchase(db, s.id, _req(p))
    q = packages.preview_purchase(db, s.id, _req(p, TxnChannel.bkash))
    assert q.balance_after is None
    with pytest.raises(InvalidRequest):
        packages.preview_purchase(db, s.id, _req(p, TxnChannel.points))


def test_purchase_with_exact_balance_succeeds(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("69"))
    p = bss_world.package(price=Decimal("69"))
    req = _req(p)
    assert packages.preview_purchase(db, s.id, req).balance_after == Decimal("0")
    out = packages.execute_purchase(
        db, s.id, req, action_id=_confirm(db, s, req), actor=Actor.portal
    )
    assert out.main_balance == Decimal("0")


def test_execute_requires_verified_otp(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("500"))
    p = bss_world.package(price=Decimal("69"))
    with pytest.raises(OtpInvalid):
        packages.execute_purchase(db, s.id, _req(p), action_id=uuid4(), actor=Actor.agent)


def test_execute_purchase_creates_subscription_and_txn(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("500"))
    p = bss_world.package(data_mb=1024, minutes=50, sms=10, validity_days=7, price=Decimal("69"))
    req = _req(p)
    aid = _confirm(db, s, req)
    out = packages.execute_purchase(db, s.id, req, action_id=aid, actor=Actor.agent)
    assert re.fullmatch(r"TXN-\d+", out.transaction_ref)
    assert out.main_balance == Decimal("431")
    txn = db.scalars(select(Transaction).where(Transaction.subscriber_id == s.id)).one()
    assert (txn.type, txn.status, txn.ref) == (
        TxnType.purchase,
        TxnStatus.success,
        out.transaction_ref,
    )
    sub = db.scalars(select(Subscription).where(Subscription.subscriber_id == s.id)).one()
    assert (sub.data_left_mb, sub.minutes_left, sub.sms_left) == (1024, 50, 10)
    assert sub.status.value == "active"
    assert sub.expires_at == out.expires_at
    n = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.subscriber_id == s.id, AuditEvent.action == "purchase")
    )
    assert n == 1


def test_execute_purchase_same_action_twice_is_noop(bss_world, db):
    s = bss_world.subscriber(main_balance=Decimal("500"))
    p = bss_world.package(price=Decimal("69"))
    req = _req(p)
    aid = _confirm(db, s, req)
    first = packages.execute_purchase(db, s.id, req, action_id=aid, actor=Actor.agent)
    second = packages.execute_purchase(db, s.id, req, action_id=aid, actor=Actor.agent)
    assert second.transaction_ref == first.transaction_ref
    assert second.expires_at == first.expires_at
    assert second.main_balance == Decimal("431")
    count = db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.subscriber_id == s.id)
    )
    assert count == 1


def test_postpaid_balance_purchase_adds_to_bill(bss_world, db):
    s = bss_world.subscriber(plan_type=PlanType.postpaid, postpaid_due=Decimal("100"))
    p = bss_world.package(price=Decimal("69"))
    req = _req(p)
    assert packages.preview_purchase(db, s.id, req).balance_after is None
    out = packages.execute_purchase(
        db, s.id, req, action_id=_confirm(db, s, req), actor=Actor.portal
    )
    assert out.postpaid_due == Decimal("169")
    assert out.main_balance == Decimal("0")


def test_purchase_replay_from_other_subscriber_rejected(bss_world, db):
    from app.models.telco import Balance

    a = bss_world.subscriber(main_balance=Decimal("500"))
    b = bss_world.subscriber(main_balance=Decimal("500"))
    p = bss_world.package(price=Decimal("69"))
    req = _req(p)
    aid = _confirm(db, a, req)
    packages.execute_purchase(db, a.id, req, action_id=aid, actor=Actor.agent)
    with pytest.raises(OtpInvalid):
        packages.execute_purchase(db, b.id, req, action_id=aid, actor=Actor.agent)
    db.expire_all()
    assert db.get(Balance, b.id).main_balance == Decimal("500")


def _stale_first_lookup(monkeypatch):
    """Simulate a second confirmer that passed the pre-lock replay check before
    the first confirmer committed: the first `_txn.existing` call sees nothing."""
    from app.bss import _txn

    real = _txn.existing
    calls = {"n": 0}

    def fake(*args, **kwargs):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(*args, **kwargs)

    monkeypatch.setattr(_txn, "existing", fake)


def test_purchase_concurrent_confirm_replays_after_lock(bss_world, db, monkeypatch):
    from app.db.session import SessionLocal
    from app.models.telco import Balance

    s = bss_world.subscriber(main_balance=Decimal("69"))
    p = bss_world.package(price=Decimal("69"))
    req = _req(p)
    aid = _confirm(db, s, req)
    first = packages.execute_purchase(db, s.id, req, action_id=aid, actor=Actor.agent)
    other = SessionLocal()
    try:
        _stale_first_lookup(monkeypatch)
        second = packages.execute_purchase(other, s.id, req, action_id=aid, actor=Actor.portal)
    finally:
        other.rollback()
        other.close()
    assert second.transaction_ref == first.transaction_ref
    assert second.main_balance == Decimal("0")
    db.expire_all()
    assert db.get(Balance, s.id).main_balance == Decimal("0")
    where = Transaction.subscriber_id == s.id
    assert db.scalar(select(func.count()).select_from(Transaction).where(where)) == 1
    assert db.scalar(
        select(func.count()).select_from(Subscription).where(Subscription.subscriber_id == s.id)
    ) == 1
    assert db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.subscriber_id == s.id, AuditEvent.action.not_in(("otp_issue", "otp_verify")))
    ) == 1
