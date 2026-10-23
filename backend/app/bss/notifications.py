"""Proactive notices: the rule-based nudge sweep and the portal inbox."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agent.telco_format import format_data
from app.bss.clock import local_tz, utc_now
from app.bss.errors import NotificationNotFound
from app.bss.types import NotificationView
from app.models.telco import (
    Balance,
    Notification,
    NotificationKind,
    Package,
    PlanType,
    Subscriber,
    SubscriberStatus,
    Subscription,
    SubscriptionStatus,
)

EXPIRY_WINDOW = timedelta(days=3)
LOW_BALANCE_BELOW = Decimal("50")
LOW_DATA_FRACTION = 0.10


def notify(
    db: Session,
    subscriber_id: UUID,
    kind: NotificationKind,
    subject_key: str,
    payload: dict[str, Any],
) -> bool:
    """Inserts one notice; True when it was new. The caller commits."""
    result = db.execute(
        insert(Notification)
        .values(subscriber_id=subscriber_id, kind=kind, subject_key=subject_key, payload=payload)
        .on_conflict_do_nothing(constraint="uq_notification_subject")
        .returning(Notification.id)
    )
    return result.first() is not None


def run_sweep(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """Applies the pack_expiring, low_balance and low_data rules to active
    subscribers and commits. Returns how many new notices each kind produced."""
    now = now or utc_now()
    counts = {
        NotificationKind.pack_expiring.value: 0,
        NotificationKind.low_balance.value: 0,
        NotificationKind.low_data.value: 0,
    }
    active = (
        Subscriber.status == SubscriberStatus.active,
        Subscription.status == SubscriptionStatus.active,
    )

    expiring = db.execute(
        select(Subscription, Package.name)
        .join(Package, Package.id == Subscription.package_id)
        .join(Subscriber, Subscriber.id == Subscription.subscriber_id)
        .where(
            *active,
            Subscription.auto_renew.is_(False),
            Subscription.expires_at > now,
            Subscription.expires_at <= now + EXPIRY_WINDOW,
        )
    )
    for sub, name in expiring:
        if notify(
            db,
            sub.subscriber_id,
            NotificationKind.pack_expiring,
            str(sub.id),
            {"package_name": name, "expires_at": sub.expires_at.isoformat()},
        ):
            counts["pack_expiring"] += 1

    day = now.astimezone(local_tz()).date().isoformat()
    low_balance = db.execute(
        select(Balance)
        .join(Subscriber, Subscriber.id == Balance.subscriber_id)
        .where(
            Subscriber.status == SubscriberStatus.active,
            Subscriber.plan_type == PlanType.prepaid,
            Balance.main_balance < LOW_BALANCE_BELOW,
        )
    ).scalars()
    for bal in low_balance:
        if notify(
            db,
            bal.subscriber_id,
            NotificationKind.low_balance,
            day,
            {"balance": float(bal.main_balance)},
        ):
            counts["low_balance"] += 1

    low_data = db.execute(
        select(Subscription, Package.name)
        .join(Package, Package.id == Subscription.package_id)
        .join(Subscriber, Subscriber.id == Subscription.subscriber_id)
        .where(
            *active,
            Package.data_mb > 0,
            Subscription.data_left_mb < Package.data_mb * LOW_DATA_FRACTION,
        )
    )
    for sub, name in low_data:
        if notify(
            db,
            sub.subscriber_id,
            NotificationKind.low_data,
            str(sub.id),
            {"package_name": name, "data_left_mb": sub.data_left_mb},
        ):
            counts["low_data"] += 1

    db.commit()
    return counts


def _money(value: Any) -> str:
    return f"৳ {Decimal(str(value)):,.2f}"


CASE_STATUS_WORDS = {
    "open": "open again",
    "in_review": "being reviewed",
    "resolved": "resolved",
}


def case_status_words(status: Any) -> str:
    return CASE_STATUS_WORDS.get(str(status), "updated")


def describe(row: Notification) -> tuple[str, str]:
    """English title and body for the portal inbox."""
    p = row.payload or {}
    if row.kind is NotificationKind.pack_expiring:
        try:
            when = datetime.fromisoformat(p["expires_at"]).astimezone(local_tz())
            on = f" on {when.day} {when:%b}"
        except (KeyError, TypeError, ValueError):
            on = " soon"
        return "Pack expiring", f"Your {p.get('package_name', 'pack')} pack expires{on}."
    if row.kind is NotificationKind.low_balance:
        return "Low balance", f"Your balance is {_money(p.get('balance', 0))}."
    if row.kind is NotificationKind.low_data:
        left = format_data(int(p.get("data_left_mb", 0)))
        return "Data running low", f"Only {left} left on {p.get('package_name', 'your pack')}."
    return "Case update", f"{p.get('case_ref', 'Your case')} is {case_status_words(p.get('status'))}."


def _view(row: Notification) -> NotificationView:
    title, body = describe(row)
    return NotificationView(
        id=row.id,
        kind=row.kind,
        title=title,
        body=body,
        payload=row.payload or {},
        created_at=row.created_at,
        read_at=row.read_at,
    )


def list_for(
    db: Session, subscriber_id: UUID, *, limit: int = 20
) -> tuple[int, list[NotificationView]]:
    """Unread count (all rows) and the newest `limit` notices."""
    unread = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.subscriber_id == subscriber_id, Notification.read_at.is_(None))
    )
    rows = db.scalars(
        select(Notification)
        .where(Notification.subscriber_id == subscriber_id)
        .order_by(Notification.created_at.desc(), Notification.id)
        .limit(limit)
    )
    return unread or 0, [_view(r) for r in rows]


def mark_read(db: Session, subscriber_id: UUID, notification_id: UUID) -> NotificationView:
    row = db.get(Notification, notification_id)
    if row is None or row.subscriber_id != subscriber_id:
        raise NotificationNotFound()
    if row.read_at is None:
        row.read_at = utc_now()
        db.commit()
    return _view(row)


def mark_all_read(db: Session, subscriber_id: UUID) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.subscriber_id == subscriber_id, Notification.read_at.is_(None))
        .values(read_at=utc_now())
    )
    db.commit()
    return result.rowcount
