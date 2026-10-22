from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.telco import PackageKind, PlanType, TxnChannel, UsageKind


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Allowance(_Base):
    data_left_mb: int
    minutes_left: int
    sms_left: int


class SubscriptionView(_Base):
    package_code: str
    package_name: str
    data_left_mb: int
    minutes_left: int
    sms_left: int
    expires_at: datetime
    auto_renew: bool


class AccountSummary(_Base):
    subscriber_id: UUID
    full_name: str
    masked_msisdn: str
    plan_type: PlanType
    district: str
    main_balance: Decimal
    postpaid_due: Decimal
    reward_points: int
    totals: Allowance
    subscriptions: list[SubscriptionView]
    nearest_expiry: datetime | None
    open_cases: int
    district_incidents: int


class UsageTotals(_Base):
    kind: UsageKind
    amount: Decimal
    unit: str
    charge: Decimal


class UsageBreakdown(_Base):
    period_days: int
    totals: list[UsageTotals]
    # Data MB per local day, oldest first.
    daily: list[tuple[date, Decimal]]


class Deduction(_Base):
    occurred_at: datetime
    description: str
    amount: Decimal
    source: Literal["usage", "purchase"]


class PackageView(_Base):
    code: str
    name: str
    kind: PackageKind
    data_mb: int
    minutes: int
    sms: int
    validity_days: int
    price: Decimal
    tag: str | None


class Recommendation(_Base):
    package: PackageView
    reason: str


class PurchaseRequest(_Base):
    package_code: str
    pay_from: TxnChannel


class PurchaseQuote(_Base):
    request: PurchaseRequest
    package: PackageView
    pay_from: TxnChannel
    price: Decimal
    balance_after: Decimal | None


class PurchaseResult(_Base):
    transaction_ref: str
    package: PackageView
    expires_at: datetime
    main_balance: Decimal
    postpaid_due: Decimal
