"""Package catalogue: search, usage-based recommendation, and OTP-gated purchase."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss import _txn, audit, otp
from app.bss.clock import utc_now
from app.bss.errors import (
    InsufficientBalance,
    InvalidRequest,
    PackageNotFound,
    SubscriberNotFound,
)
from app.bss.types import (
    PackageView,
    PurchaseQuote,
    PurchaseRequest,
    PurchaseResult,
    Recommendation,
)
from app.models.telco import (
    Actor,
    Balance,
    Package,
    PackageKind,
    PlanType,
    Subscriber,
    Subscription,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
    UsageEvent,
    UsageKind,
)

_PAY_CHANNELS = {TxnChannel.balance, TxnChannel.bkash, TxnChannel.nagad, TxnChannel.card}


def _view(p: Package) -> PackageView:
    return PackageView.model_validate(p)


def search(
    db: Session,
    *,
    kind: PackageKind | None = None,
    max_price: Decimal | None = None,
    min_data_gb: float | None = None,
    validity_days: int | None = None,
) -> list[PackageView]:
    q = select(Package).where(Package.is_active.is_(True))
    if kind is not None:
        q = q.where(Package.kind == kind)
    if max_price is not None:
        q = q.where(Package.price <= max_price)
    if min_data_gb is not None:
        q = q.where(Package.data_mb >= min_data_gb * 1024)
    if validity_days is not None:
        q = q.where(Package.validity_days == validity_days)
    rows = db.scalars(q.order_by(Package.price.asc(), Package.code.asc())).all()
    return [_view(p) for p in rows]


def recommend(
    db: Session,
    subscriber_id: uuid.UUID,
    *,
    now: datetime | None = None,
    limit: int = 3,
) -> list[Recommendation]:
    now = now or utc_now()
    since = now - timedelta(days=30)

    def used(kind: UsageKind) -> float:
        return float(
            db.scalar(
                select(func.coalesce(func.sum(UsageEvent.amount), 0)).where(
                    UsageEvent.subscriber_id == subscriber_id,
                    UsageEvent.kind == kind,
                    UsageEvent.occurred_at >= since,
                    UsageEvent.occurred_at <= now,
                )
            )
        )

    need_data = used(UsageKind.data)
    need_min = used(UsageKind.voice)
    q = select(Package).where(Package.is_active.is_(True))
    if need_data > 0 and need_min > 0:
        q = q.where(Package.kind == PackageKind.bundle)
    elif need_data > 0:
        q = q.where(Package.kind == PackageKind.data)
    elif need_min > 0:
        q = q.where(Package.kind == PackageKind.voice)

    scored: list[tuple[float, float, Package]] = []
    for p in db.scalars(q).all():
        f = 30 / p.validity_days
        coverage = (
            (min(1.0, p.data_mb * f / need_data) if need_data else 1.0)
            + (min(1.0, p.minutes * f / need_min) if need_min else 1.0)
        ) / 2
        scored.append((coverage, float(p.price) * f, p))
    scored.sort(key=lambda t: (-round(t[0], 1), t[1]))
    return [
        Recommendation(
            package=_view(p),
            reason=f"Covers {_coverage_words(cov)} your last 30 days' use for ৳{cost:.0f}/month",
        )
        for cov, cost, p in scored[:limit]
    ]


def _coverage_words(coverage: float) -> str:
    """How much of their usage a pack covers, as a person would say it: the
    agent reads this out, and "86%" sounds like a spreadsheet."""
    if coverage >= 0.95:
        return "all of"
    if coverage >= 0.7:
        return "most of"
    if coverage >= 0.4:
        return "about half of"
    return "a small part of"


def _lock_balance(db: Session, subscriber_id: uuid.UUID) -> Balance | None:
    """SELECT ... FOR UPDATE on the balance row, refreshing any stale copy."""
    return db.scalar(
        select(Balance)
        .where(Balance.subscriber_id == subscriber_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def _check(
    db: Session, subscriber_id: uuid.UUID, req: PurchaseRequest
) -> tuple[Package, Subscriber, Balance, Decimal | None]:
    pkg = db.scalar(
        select(Package).where(Package.code == req.package_code, Package.is_active.is_(True))
    )
    if pkg is None:
        raise PackageNotFound()
    if req.pay_from not in _PAY_CHANNELS:
        raise InvalidRequest(f"Cannot pay for a package from {req.pay_from.value}")
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise SubscriberNotFound()
    bal = db.scalar(select(Balance).where(Balance.subscriber_id == subscriber_id))
    if bal is None:
        raise SubscriberNotFound()
    balance_after: Decimal | None = None
    if req.pay_from == TxnChannel.balance and sub.plan_type == PlanType.prepaid:
        if bal.main_balance < pkg.price:
            raise InsufficientBalance()
        balance_after = bal.main_balance - pkg.price
    return pkg, sub, bal, balance_after


def preview_purchase(
    db: Session, subscriber_id: uuid.UUID, req: PurchaseRequest
) -> PurchaseQuote:
    pkg, _, _, balance_after = _check(db, subscriber_id, req)
    return PurchaseQuote(
        request=req,
        package=_view(pkg),
        pay_from=req.pay_from,
        price=pkg.price,
        balance_after=balance_after,
    )


def _result_from(db: Session, txn: Transaction) -> PurchaseResult:
    pkg = db.get(Package, txn.package_id)
    bal = db.get(Balance, txn.subscriber_id)
    db.refresh(bal)
    return PurchaseResult(
        transaction_ref=txn.ref,
        package=_view(pkg),
        # The transaction is stamped with the same `now` as the subscription.
        expires_at=txn.created_at + timedelta(days=pkg.validity_days),
        main_balance=bal.main_balance,
        postpaid_due=bal.postpaid_due,
    )


def grant_package(db: Session, subscriber_id: uuid.UUID, pkg: Package, now: datetime) -> datetime:
    """Add a fresh subscription for `pkg`; returns its expiry. Caller commits."""
    expires_at = now + timedelta(days=pkg.validity_days)
    db.add(
        Subscription(
            subscriber_id=subscriber_id,
            package_id=pkg.id,
            data_left_mb=pkg.data_mb,
            minutes_left=pkg.minutes,
            sms_left=pkg.sms,
            activated_at=now,
            expires_at=expires_at,
            auto_renew=pkg.auto_renewable,
        )
    )
    return expires_at


def execute_purchase(
    db: Session,
    subscriber_id: uuid.UUID,
    req: PurchaseRequest,
    *,
    action_id: uuid.UUID,
    actor: Actor,
    now: datetime | None = None,
) -> PurchaseResult:
    now = now or utc_now()
    existing = _txn.existing(db, subscriber_id, action_id, TxnType.purchase)
    if existing is not None:
        return _result_from(db, existing)
    otp.require_verified(
        db,
        subscriber_id=subscriber_id,
        action_id=action_id,
        purpose="purchase",
        payload=req.model_dump(mode="json"),
        now=now,
    )
    _lock_balance(db, subscriber_id)
    # A concurrent confirmer of the same action may have committed while we
    # waited for the lock: hand back its result rather than re-checking.
    existing = _txn.existing(db, subscriber_id, action_id, TxnType.purchase)
    if existing is not None:
        db.rollback()
        return _result_from(db, existing)
    pkg, sub, bal, _ = _check(db, subscriber_id, req)
    if req.pay_from == TxnChannel.balance:
        if sub.plan_type == PlanType.prepaid:
            bal.main_balance = bal.main_balance - pkg.price
        else:
            bal.postpaid_due = bal.postpaid_due + pkg.price
    expires_at = grant_package(db, subscriber_id, pkg, now)
    ref = _txn.next_ref(db)
    db.add(
        Transaction(
            ref=ref,
            subscriber_id=subscriber_id,
            action_id=action_id,
            type=TxnType.purchase,
            channel=req.pay_from,
            amount=pkg.price,
            package_id=pkg.id,
            status=TxnStatus.success,
            created_at=now,
        )
    )
    audit.record(
        db,
        actor=actor,
        action="purchase",
        subscriber_id=subscriber_id,
        action_id=action_id,
        detail={"package": pkg.code, "pay_from": req.pay_from.value, "ref": ref},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _txn.existing(db, subscriber_id, action_id, TxnType.purchase)
        if existing is None:
            raise
        return _result_from(db, existing)
    return PurchaseResult(
        transaction_ref=ref,
        package=_view(pkg),
        expires_at=expires_at,
        main_balance=bal.main_balance,
        postpaid_due=bal.postpaid_due,
    )
