"""Read-only transaction history for a subscriber."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bss.clock import utc_now
from app.bss.types import TransactionView
from app.models.telco import Offer, Package, Transaction, TxnStatus, TxnType


def lookup(
    db: Session,
    subscriber_id: uuid.UUID,
    *,
    type: TxnType | None = None,
    status: TxnStatus | None = None,
    ref: str | None = None,
    days: int = 30,
    now: datetime | None = None,
    limit: int = 10,
) -> list[TransactionView]:
    now = now or utc_now()
    q = (
        select(Transaction, Package.name, Offer.points_cost)
        .outerjoin(Package, Package.id == Transaction.package_id)
        .outerjoin(Offer, Offer.id == Transaction.offer_id)
        .where(Transaction.subscriber_id == subscriber_id)
    )
    if ref is not None:
        q = q.where(func.lower(Transaction.ref) == ref.strip().lower())
    else:
        q = q.where(Transaction.created_at >= now - timedelta(days=days))
    if type is not None:
        q = q.where(Transaction.type == type)
    if status is not None:
        q = q.where(Transaction.status == status)
    rows = db.execute(q.order_by(Transaction.created_at.desc()).limit(limit)).all()
    return [view(t, name, points) for t, name, points in rows]


def view(
    t: Transaction,
    package_name: str | None,
    points_cost: int | None,
    *,
    target_msisdn: str | None = None,
) -> TransactionView:
    """One transaction as the API shape; `points_cost` is its offer's cost (redeems only)."""
    return TransactionView(
        ref=t.ref,
        type=t.type,
        channel=t.channel,
        amount=t.amount,
        target_msisdn=target_msisdn if target_msisdn is not None else t.target_msisdn,
        status=t.status,
        failure_reason=t.failure_reason,
        created_at=t.created_at,
        package_name=package_name,
        points_spent=points_cost if t.type == TxnType.redeem else None,
    )
