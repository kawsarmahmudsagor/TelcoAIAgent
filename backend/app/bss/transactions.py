"""Read-only transaction history for a subscriber."""

import re
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bss.clock import utc_now
from app.bss.otp import BENGALI_DIGITS as _BENGALI_DIGITS
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
    q = (
        select(Transaction, Package.name, Offer.points_cost)
        .outerjoin(Package, Package.id == Transaction.package_id)
        .outerjoin(Offer, Offer.id == Transaction.offer_id)
        .where(*_conditions(subscriber_id, type, status, ref, days, now or utc_now()))
    )
    rows = db.execute(q.order_by(Transaction.created_at.desc()).limit(limit)).all()
    return [view(t, name, points) for t, name, points in rows]


def count(
    db: Session,
    subscriber_id: uuid.UUID,
    *,
    type: TxnType | None = None,
    status: TxnStatus | None = None,
    ref: str | None = None,
    days: int = 30,
    now: datetime | None = None,
) -> int:
    """How many transactions lookup would find with no limit."""
    conds = _conditions(subscriber_id, type, status, ref, days, now or utc_now())
    return db.scalar(select(func.count()).select_from(Transaction).where(*conds)) or 0


def normalise_ref(raw: str) -> str:
    """'txn 840221', 'TXN840221', ' TXN-840221 ' and '840221' all mean 'TXN-840221'."""
    s = re.sub(r"[\s-]", "", raw.translate(_BENGALI_DIGITS)).upper()
    if s.isdigit():
        return f"TXN-{s}"
    return f"TXN-{s[3:]}" if s.startswith("TXN") else s


def _conditions(subscriber_id, type, status, ref, days, now) -> list:
    conds = [Transaction.subscriber_id == subscriber_id]
    if ref is not None:
        conds.append(Transaction.ref == normalise_ref(ref))
    else:
        conds.append(Transaction.created_at >= now - timedelta(days=days))
    if type is not None:
        conds.append(Transaction.type == type)
    if status is not None:
        conds.append(Transaction.status == status)
    return conds


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
        points_earned=t.points_earned if t.type == TxnType.recharge else None,
    )
