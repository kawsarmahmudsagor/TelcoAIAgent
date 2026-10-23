"""Recharge: validation, limits, cashback and OTP-gated execution."""

import re
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss import _txn, audit, otp
from app.bss.accounts import mask_msisdn
from app.bss.clock import local_day_bounds, local_tz, utc_now
from app.bss.errors import InvalidMsisdn, InvalidRequest, LimitExceeded, SubscriberNotFound
from app.bss.types import RechargeQuote, RechargeRequest, RechargeResult
from app.models.telco import (
    Actor,
    Balance,
    Offer,
    OfferAudience,
    PlanType,
    Subscriber,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
)

_CHANNELS = {TxnChannel.bkash, TxnChannel.nagad, TxnChannel.card}
_MSISDN = re.compile(r"^01[3-9]\d{8}$")
MIN_AMOUNT = Decimal("20")
MAX_AMOUNT = Decimal("1000")
DAILY_CAP = Decimal("5000")


def _normalise(raw: str) -> str:
    s = re.sub(r"[\s-]", "", raw)
    if s.startswith("+88"):
        s = s[3:]
    elif s.startswith("88") and len(s) == 13:
        s = s[2:]
    if not _MSISDN.fullmatch(s):
        raise InvalidMsisdn()
    return s


def _cashback(db: Session, sub: Subscriber, amount: Decimal, now: datetime) -> Decimal:
    today = now.astimezone(local_tz()).date()
    audiences = [OfferAudience.all, OfferAudience(sub.plan_type.value)]
    offers = db.scalars(
        select(Offer).where(
            Offer.is_active.is_(True),
            Offer.cashback_percent.is_not(None),
            Offer.audience.in_(audiences),
            or_(Offer.min_recharge.is_(None), Offer.min_recharge <= amount),
            or_(Offer.starts_on.is_(None), Offer.starts_on <= today),
            or_(Offer.ends_on.is_(None), Offer.ends_on >= today),
        )
    ).all()
    best = Decimal("0")
    for o in offers:
        value = amount * o.cashback_percent / 100
        if o.cashback_cap is not None:
            value = min(value, o.cashback_cap)
        best = max(best, value)
    return best.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _check(
    db: Session, subscriber_id: uuid.UUID, req: RechargeRequest, now: datetime
) -> tuple[Subscriber, str, bool, Decimal]:
    if req.channel not in _CHANNELS:
        raise InvalidRequest(f"Cannot recharge from {req.channel.value}")
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise SubscriberNotFound()
    target = _normalise(req.target_msisdn) if req.target_msisdn else sub.msisdn
    if req.amount < MIN_AMOUNT or req.amount > MAX_AMOUNT:
        raise LimitExceeded(f"Recharge must be between {MIN_AMOUNT} and {MAX_AMOUNT}")
    start, end = local_day_bounds(now)
    today_total = db.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.subscriber_id == subscriber_id,
            Transaction.type == TxnType.recharge,
            Transaction.status == TxnStatus.success,
            Transaction.created_at >= start,
            Transaction.created_at < end,
        )
    )
    if today_total + req.amount > DAILY_CAP:
        raise LimitExceeded(f"Daily recharge limit of {DAILY_CAP} reached")
    own = target == sub.msisdn
    # Cashback is credited to the caller's own balance, so only prepaid callers
    # recharging their own number get it.
    prepaid_own = own and sub.plan_type == PlanType.prepaid
    cashback = _cashback(db, sub, req.amount, now) if prepaid_own else Decimal("0.00")
    return sub, target, own, cashback


def preview_recharge(
    db: Session, subscriber_id: uuid.UUID, req: RechargeRequest, *, now: datetime | None = None
) -> RechargeQuote:
    _, target, own, cashback = _check(db, subscriber_id, req, now or utc_now())
    return RechargeQuote(request=req, target_msisdn=target, is_own_number=own, cashback=cashback)


def _result_from(db: Session, txn: Transaction) -> RechargeResult:
    bal = db.get(Balance, txn.subscriber_id)
    db.refresh(bal)
    return RechargeResult(
        transaction_ref=txn.ref,
        amount=txn.amount,
        cashback=txn.cashback,
        target_msisdn=txn.target_msisdn,
        main_balance=bal.main_balance,
        postpaid_due=bal.postpaid_due,
    )


def execute_recharge(
    db: Session,
    subscriber_id: uuid.UUID,
    req: RechargeRequest,
    *,
    action_id: uuid.UUID,
    actor: Actor,
    now: datetime | None = None,
) -> RechargeResult:
    now = now or utc_now()
    existing = _txn.existing(db, subscriber_id, action_id, TxnType.recharge)
    if existing is not None:
        return _result_from(db, existing)
    otp.require_verified(
        db,
        subscriber_id=subscriber_id,
        action_id=action_id,
        purpose="recharge",
        payload=req.model_dump(mode="json"),
        now=now,
    )
    # Lock the caller's (and a known target's) balance rows in a deterministic
    # order so crossing recharges cannot deadlock, and so the daily-cap check
    # below is serialised per subscriber.
    caller = db.get(Subscriber, subscriber_id)
    if caller is None:
        raise SubscriberNotFound()
    target = _normalise(req.target_msisdn) if req.target_msisdn else caller.msisdn
    target_sub = db.scalar(select(Subscriber).where(Subscriber.msisdn == target))
    ids = sorted({subscriber_id} | ({target_sub.id} if target_sub else set()), key=str)
    locked = {
        b.subscriber_id: b
        for b in db.scalars(
            select(Balance)
            .where(Balance.subscriber_id.in_(ids))
            .order_by(Balance.subscriber_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    # A concurrent confirmer of the same action may have committed while we
    # waited for the locks: hand back its result rather than re-checking limits.
    existing = _txn.existing(db, subscriber_id, action_id, TxnType.recharge)
    if existing is not None:
        db.rollback()
        return _result_from(db, existing)
    own_bal = locked.get(subscriber_id)
    if own_bal is None:
        raise SubscriberNotFound()
    _, target, own, cashback = _check(db, subscriber_id, req, now)
    if target_sub is not None:
        tbal = locked.get(target_sub.id)
        if tbal is not None:
            if target_sub.plan_type == PlanType.prepaid:
                tbal.main_balance = tbal.main_balance + req.amount + (cashback if own else 0)
            else:
                tbal.postpaid_due = max(Decimal("0"), tbal.postpaid_due - req.amount)
    ref = _txn.next_ref(db)
    db.add(
        Transaction(
            ref=ref,
            subscriber_id=subscriber_id,
            action_id=action_id,
            type=TxnType.recharge,
            channel=req.channel,
            amount=req.amount,
            target_msisdn=target,
            cashback=cashback,
            status=TxnStatus.success,
            created_at=now,
        )
    )
    audit.record(
        db,
        actor=actor,
        action="recharge",
        subscriber_id=subscriber_id,
        action_id=action_id,
        detail={
            "amount": str(req.amount),
            "channel": req.channel.value,
            "target_masked": mask_msisdn(target),
            "cashback": str(cashback),
            "ref": ref,
        },
    )
    if not own:
        audit.record(
            db,
            actor=actor,
            action="target_credit",
            subscriber_id=target_sub.id if target_sub else None,
            action_id=action_id,
            detail={
                "ref": ref,
                "amount": str(req.amount),
                "from_masked": mask_msisdn(caller.msisdn),
            },
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _txn.existing(db, subscriber_id, action_id, TxnType.recharge)
        if existing is None:
            raise
        return _result_from(db, existing)
    db.refresh(own_bal)
    return RechargeResult(
        transaction_ref=ref,
        amount=req.amount,
        cashback=cashback,
        target_msisdn=target,
        main_balance=own_bal.main_balance,
        postpaid_due=own_bal.postpaid_due,
    )
