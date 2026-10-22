from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.telco import (
    CasePriority,
    CaseSource,
    CaseStatus,
    IncidentKind,
    IncidentStatus,
    PackageKind,
    PlanType,
    TxnChannel,
    TxnStatus,
    TxnType,
    UsageKind,
)


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


class RechargeRequest(_Base):
    amount: Decimal
    channel: TxnChannel
    target_msisdn: str | None = None

    @field_validator("amount")
    @classmethod
    def _two_places(cls, v: Decimal) -> Decimal:
        # "100" and "100.00" must hash (OTP binding) and store identically.
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class RechargeQuote(_Base):
    request: RechargeRequest
    target_msisdn: str
    is_own_number: bool
    cashback: Decimal


class RechargeResult(_Base):
    transaction_ref: str
    amount: Decimal
    cashback: Decimal
    target_msisdn: str
    main_balance: Decimal | None
    postpaid_due: Decimal | None


class TransactionView(_Base):
    ref: str
    type: TxnType
    channel: TxnChannel
    amount: Decimal
    target_msisdn: str | None
    status: TxnStatus
    failure_reason: str | None
    created_at: datetime
    package_name: str | None


class OfferView(_Base):
    id: UUID
    title: str
    description: str | None
    terms: str | None
    points_cost: int | None
    cashback_percent: Decimal | None
    cashback_cap: Decimal | None
    min_recharge: Decimal | None
    package: PackageView | None
    ends_on: date | None


class OffersAndPoints(_Base):
    reward_points: int
    offers: list[OfferView]


class RedeemQuote(_Base):
    offer: OfferView
    points_after: int


class RedeemResult(_Base):
    transaction_ref: str
    offer_title: str
    reward_points: int
    expires_at: datetime | None


class CaseView(_Base):
    ref: str
    category: str
    description: str
    priority: CasePriority
    status: CaseStatus
    source: CaseSource
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None


class IncidentView(_Base):
    district: str
    area: str
    kind: IncidentKind
    status: IncidentStatus
    message: str
    starts_at: datetime
    ends_at: datetime | None
