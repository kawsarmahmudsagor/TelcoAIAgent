"""The telco BSS data: subscribers, balances, packages and subscriptions, usage,
transactions, support cases, network incidents, OTP challenges, notifications,
the audit trail and offers. app.bss works on these; the agent and the API go
through app.bss, never straight to the tables."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampedBase


class PlanType(str, enum.Enum):
    prepaid = "prepaid"
    postpaid = "postpaid"


class SubscriberStatus(str, enum.Enum):
    active = "active"
    suspended = "suspended"


class PackageKind(str, enum.Enum):
    data = "data"
    voice = "voice"
    bundle = "bundle"
    sms = "sms"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    expired = "expired"


class UsageKind(str, enum.Enum):
    data = "data"
    voice = "voice"
    sms = "sms"
    vas = "vas"


class TxnType(str, enum.Enum):
    recharge = "recharge"
    purchase = "purchase"
    redeem = "redeem"


class TxnChannel(str, enum.Enum):
    bkash = "bkash"
    nagad = "nagad"
    card = "card"
    balance = "balance"
    points = "points"


class TxnStatus(str, enum.Enum):
    success = "success"
    pending = "pending"
    failed = "failed"


class CasePriority(str, enum.Enum):
    normal = "normal"
    high = "high"


class CaseStatus(str, enum.Enum):
    open = "open"
    in_review = "in_review"
    resolved = "resolved"


class CaseSource(str, enum.Enum):
    agent = "agent"
    portal = "portal"
    admin = "admin"


class IncidentKind(str, enum.Enum):
    outage = "outage"
    congestion = "congestion"
    maintenance = "maintenance"


class IncidentStatus(str, enum.Enum):
    investigating = "investigating"
    scheduled = "scheduled"
    resolved = "resolved"


class NotificationKind(str, enum.Enum):
    pack_expiring = "pack_expiring"
    low_balance = "low_balance"
    low_data = "low_data"
    case_update = "case_update"


class OfferAudience(str, enum.Enum):
    all = "all"
    prepaid = "prepaid"
    postpaid = "postpaid"
    specific = "specific"


class Actor(str, enum.Enum):
    agent = "agent"
    portal = "portal"
    admin = "admin"
    system = "system"


# Human-facing references: f"TXN-{nextval}" and f"TC-{nextval}".
txn_ref_seq = Sequence("txn_ref_seq", start=840220, metadata=Base.metadata)
case_ref_seq = Sequence("case_ref_seq", start=2049, metadata=Base.metadata)


def _subscriber_fk(**kwargs: Any) -> Any:
    return mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="CASCADE"), **kwargs
    )


class Subscriber(TimestampedBase):
    __tablename__ = "subscribers"

    # Local 11-digit number, e.g. 01712345678.
    msisdn: Mapped[str] = mapped_column(String(11), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    plan_type: Mapped[PlanType] = mapped_column(Enum(PlanType, name="plan_type"))
    district: Mapped[str] = mapped_column(String(60))
    status: Mapped[SubscriberStatus] = mapped_column(
        Enum(SubscriberStatus, name="subscriber_status"),
        default=SubscriberStatus.active,
        server_default=SubscriberStatus.active.value,
    )
    joined_on: Mapped[date] = mapped_column(Date)
    reward_points: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    preferred_language: Mapped[str] = mapped_column(String(2), default="bn", server_default="bn")
    # bcrypt hash; NULL for the seeded personas until they reset a password.
    password_hash: Mapped[str | None] = mapped_column(String(60), nullable=True)


class Balance(Base):
    """One row per subscriber: prepaid main balance and postpaid amount due."""

    __tablename__ = "balances"

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True
    )
    main_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), server_default="0"
    )
    postpaid_due: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Package(TimestampedBase):
    """A purchasable data / voice / SMS pack or bundle."""

    __tablename__ = "packages"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[PackageKind] = mapped_column(Enum(PackageKind, name="package_kind"))
    data_mb: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    minutes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    validity_days: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    tag: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Subscription(TimestampedBase):
    """A package a subscriber bought, with what is left of it."""

    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subscriptions_subscriber_status", "subscriber_id", "status"),)

    subscriber_id: Mapped[uuid.UUID] = _subscriber_fk()
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("packages.id"))
    data_left_mb: Mapped[int] = mapped_column(Integer)
    minutes_left: Mapped[int] = mapped_column(Integer)
    sms_left: Mapped[int] = mapped_column(Integer)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        default=SubscriptionStatus.active,
        server_default=SubscriptionStatus.active.value,
    )


class UsageEvent(TimestampedBase):
    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_subscriber_occurred", "subscriber_id", "occurred_at"),
    )

    subscriber_id: Mapped[uuid.UUID] = _subscriber_fk()
    kind: Mapped[UsageKind] = mapped_column(Enum(UsageKind, name="usage_kind"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # "MB", "min", "sms" or "item".
    unit: Mapped[str] = mapped_column(String(8))
    charge: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), server_default="0"
    )
    description: Mapped[str] = mapped_column(String(160))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Transaction(TimestampedBase):
    """A recharge, pack purchase or points redemption."""

    __tablename__ = "transactions"

    # f"TXN-{nextval('txn_ref_seq')}".
    ref: Mapped[str] = mapped_column(String(16), unique=True)
    subscriber_id: Mapped[uuid.UUID] = _subscriber_fk()
    # Idempotency key of the write that made it.
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=True
    )
    type: Mapped[TxnType] = mapped_column(Enum(TxnType, name="txn_type"))
    channel: Mapped[TxnChannel] = mapped_column(Enum(TxnChannel, name="txn_channel"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    target_msisdn: Mapped[str | None] = mapped_column(String(11), nullable=True)
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("packages.id"), nullable=True
    )
    offer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offers.id"), nullable=True
    )
    cashback: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), server_default="0"
    )
    # Reward points a recharge earned the payer (1 per full ৳10).
    points_earned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[TxnStatus] = mapped_column(Enum(TxnStatus, name="txn_status"))
    failure_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)


class SupportCase(TimestampedBase):
    __tablename__ = "support_cases"

    # f"TC-{nextval('case_ref_seq')}".
    ref: Mapped[str] = mapped_column(String(12), unique=True)
    subscriber_id: Mapped[uuid.UUID] = _subscriber_fk()
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=True
    )
    category: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[CasePriority] = mapped_column(
        Enum(CasePriority, name="case_priority"),
        default=CasePriority.normal,
        server_default=CasePriority.normal.value,
    )
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, name="case_status"),
        default=CaseStatus.open,
        server_default=CaseStatus.open.value,
    )
    source: Mapped[CaseSource] = mapped_column(Enum(CaseSource, name="case_source"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NetworkIncident(TimestampedBase):
    """An outage, congestion or planned maintenance in an area of a district."""

    __tablename__ = "network_incidents"

    district: Mapped[str] = mapped_column(String(60))
    area: Mapped[str] = mapped_column(String(120))
    kind: Mapped[IncidentKind] = mapped_column(Enum(IncidentKind, name="incident_kind"))
    status: Mapped[IncidentStatus] = mapped_column(Enum(IncidentStatus, name="incident_status"))
    message: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OtpChallenge(TimestampedBase):
    """A one-time code guarding one write, bound to (subscriber, action_id,
    purpose, request_hash). Only the code's hash is stored."""

    __tablename__ = "otp_challenges"

    subscriber_id: Mapped[uuid.UUID] = _subscriber_fk()
    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True)
    purpose: Mapped[str] = mapped_column(String(32))
    request_hash: Mapped[str] = mapped_column(String(64))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(TimestampedBase):
    """One proactive notice per (subscriber, kind, subject), so a sweep that runs
    again never repeats it."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "subscriber_id", "kind", "subject_key", name="uq_notification_subject"
        ),
    )

    subscriber_id: Mapped[uuid.UUID] = _subscriber_fk()
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(NotificationKind, name="notification_kind")
    )
    subject_key: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(TimestampedBase):
    """One row per write, whoever made it."""

    __tablename__ = "audit_events"

    # The trail outlives the subscriber it was about.
    subscriber_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="SET NULL"), nullable=True
    )
    actor: Mapped[Actor] = mapped_column(Enum(Actor, name="audit_actor"))
    action: Mapped[str] = mapped_column(String(40))
    action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OfferSubscriber(Base):
    """Audience list for offers with audience=specific."""

    __tablename__ = "offer_subscribers"

    offer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offers.id", ondelete="CASCADE"), primary_key=True
    )
    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscribers.id", ondelete="CASCADE"), primary_key=True
    )


class Offer(TimestampedBase):
    """A promotion: a discounted pack, a points redemption or recharge cashback."""

    __tablename__ = "offers"

    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("packages.id"), nullable=True
    )
    points_cost: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cashback_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    cashback_cap: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    min_recharge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    audience: Mapped[OfferAudience] = mapped_column(
        Enum(OfferAudience, name="offer_audience"),
        default=OfferAudience.all,
        server_default=OfferAudience.all.value,
    )
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    subscribers: Mapped[list[Subscriber]] = relationship(
        secondary="offer_subscribers", order_by="Subscriber.full_name"
    )
