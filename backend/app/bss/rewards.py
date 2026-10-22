"""Reward points and offers: listing and OTP-gated redemption."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss import _txn, audit, otp
from app.bss.clock import local_tz, utc_now
from app.bss.errors import InsufficientPoints, OfferNotEligible, SubscriberNotFound
from app.bss.packages import grant_package
from app.bss.types import OffersAndPoints, OfferView, PackageView, RedeemQuote, RedeemResult
from app.models.telco import (
    Actor,
    Offer,
    OfferAudience,
    Package,
    Subscriber,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
)


def _view(db: Session, o: Offer) -> OfferView:
    pkg = db.get(Package, o.package_id) if o.package_id else None
    return OfferView(
        id=o.id,
        title=o.title,
        description=o.description,
        terms=o.terms,
        points_cost=o.points_cost,
        cashback_percent=o.cashback_percent,
        cashback_cap=o.cashback_cap,
        min_recharge=o.min_recharge,
        package=PackageView.model_validate(pkg) if pkg else None,
        ends_on=o.ends_on,
    )


def _eligible(db: Session, sub: Subscriber, now: datetime) -> list[Offer]:
    today = now.astimezone(local_tz()).date()
    return list(
        db.scalars(
            select(Offer)
            .where(
                Offer.is_active.is_(True),
                Offer.audience.in_([OfferAudience.all, OfferAudience(sub.plan_type.value)]),
                or_(Offer.starts_on.is_(None), Offer.starts_on <= today),
                or_(Offer.ends_on.is_(None), Offer.ends_on >= today),
            )
            .order_by(Offer.created_at.asc(), Offer.title.asc())
        ).all()
    )


def _subscriber(db: Session, subscriber_id: uuid.UUID, *, lock: bool = False) -> Subscriber:
    q = select(Subscriber).where(Subscriber.id == subscriber_id)
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    sub = db.scalar(q)
    if sub is None:
        raise SubscriberNotFound()
    return sub


def get_offers_and_points(
    db: Session, subscriber_id: uuid.UUID, *, now: datetime | None = None
) -> OffersAndPoints:
    sub = _subscriber(db, subscriber_id)
    return OffersAndPoints(
        reward_points=sub.reward_points,
        offers=[_view(db, o) for o in _eligible(db, sub, now or utc_now())],
    )


def _check(db: Session, sub: Subscriber, offer_id: uuid.UUID, now: datetime) -> Offer:
    offer = next((o for o in _eligible(db, sub, now) if o.id == offer_id), None)
    if offer is None or offer.points_cost is None:
        raise OfferNotEligible()
    if sub.reward_points < offer.points_cost:
        raise InsufficientPoints()
    return offer


def preview_redeem(
    db: Session, subscriber_id: uuid.UUID, offer_id: uuid.UUID, *, now: datetime | None = None
) -> RedeemQuote:
    sub = _subscriber(db, subscriber_id)
    offer = _check(db, sub, offer_id, now or utc_now())
    return RedeemQuote(offer=_view(db, offer), points_after=sub.reward_points - offer.points_cost)


def _result_from(db: Session, txn: Transaction) -> RedeemResult:
    offer = db.get(Offer, txn.offer_id)
    pkg = db.get(Package, txn.package_id) if txn.package_id else None
    sub = db.get(Subscriber, txn.subscriber_id)
    db.refresh(sub)
    return RedeemResult(
        transaction_ref=txn.ref,
        offer_title=offer.title,
        reward_points=sub.reward_points,
        expires_at=txn.created_at + timedelta(days=pkg.validity_days) if pkg else None,
    )


def execute_redeem(
    db: Session,
    subscriber_id: uuid.UUID,
    offer_id: uuid.UUID,
    *,
    action_id: uuid.UUID,
    actor: Actor,
    now: datetime | None = None,
) -> RedeemResult:
    now = now or utc_now()
    existing = _txn.existing(db, subscriber_id, action_id, TxnType.redeem)
    if existing is not None:
        return _result_from(db, existing)
    otp.require_verified(
        db,
        subscriber_id=subscriber_id,
        action_id=action_id,
        purpose="redeem",
        payload={"offer_id": str(offer_id)},
        now=now,
    )
    sub = _subscriber(db, subscriber_id, lock=True)
    # A concurrent confirmer of the same action may have committed while we
    # waited for the lock: hand back its result rather than re-checking points.
    existing = _txn.existing(db, subscriber_id, action_id, TxnType.redeem)
    if existing is not None:
        db.rollback()
        return _result_from(db, existing)
    offer = _check(db, sub, offer_id, now)
    sub.reward_points = sub.reward_points - offer.points_cost
    pkg = db.get(Package, offer.package_id) if offer.package_id else None
    expires_at = grant_package(db, subscriber_id, pkg, now) if pkg else None
    ref = _txn.next_ref(db)
    db.add(
        Transaction(
            ref=ref,
            subscriber_id=subscriber_id,
            action_id=action_id,
            type=TxnType.redeem,
            channel=TxnChannel.points,
            amount=0,
            package_id=pkg.id if pkg else None,
            offer_id=offer.id,
            status=TxnStatus.success,
            created_at=now,
        )
    )
    audit.record(
        db,
        actor=actor,
        action="redeem",
        subscriber_id=subscriber_id,
        action_id=action_id,
        detail={"offer": offer.title, "points": offer.points_cost, "ref": ref},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _txn.existing(db, subscriber_id, action_id, TxnType.redeem)
        if existing is None:
            raise
        return _result_from(db, existing)
    return RedeemResult(
        transaction_ref=ref,
        offer_title=offer.title,
        reward_points=sub.reward_points,
        expires_at=expires_at,
    )
