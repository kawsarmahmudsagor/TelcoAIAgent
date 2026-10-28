import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.bss.types import NotificationView
from app.models.telco import CasePriority, PlanType, TxnChannel

PORTAL_CASE_CATEGORIES = (
    "recharge_not_credited",
    "unexpected_deduction",
    "package_activation",
    "network_issue",
    "billing",
    "other",
)


class PortalMe(BaseModel):
    subscriber_id: uuid.UUID
    full_name: str
    first_name: str
    msisdn: str
    masked_msisdn: str
    plan_type: PlanType
    district: str


class PortalCaseCreate(BaseModel):
    category: Literal[
        "recharge_not_credited",
        "unexpected_deduction",
        "package_activation",
        "network_issue",
        "billing",
        "other",
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=10, max_length=1000)
    ]
    priority: CasePriority = CasePriority.normal
    request_id: uuid.UUID


class PortalPurchase(BaseModel):
    kind: Literal["purchase"]
    package_code: str
    pay_from: TxnChannel


class PortalRecharge(BaseModel):
    kind: Literal["recharge"]
    amount: Decimal
    channel: TxnChannel
    target_msisdn: str | None = None


class PortalRedeem(BaseModel):
    kind: Literal["redeem"]
    offer_id: uuid.UUID


PortalAction = Annotated[
    PortalPurchase | PortalRecharge | PortalRedeem, Field(discriminator="kind")
]


class OtpSms(BaseModel):
    code: str
    to: str
    expires_at: datetime


class ActionStart(BaseModel):
    action_id: uuid.UUID
    kind: Literal["purchase", "recharge", "redeem"]
    title: str
    amount: float | None
    pay_from: str | None
    target: str | None
    points_cost: int | None
    # Reward points a recharge will earn.
    points_earned: int | None
    expires_at: datetime
    otp: OtpSms


class ActionConfirm(BaseModel):
    action: PortalAction
    code: str


class ActionResult(BaseModel):
    kind: Literal["purchase", "recharge", "redeem"]
    ref: str
    main_balance: float | None
    postpaid_due: float | None
    reward_points: int | None
    points_earned: int | None


class NotificationList(BaseModel):
    unread: int
    items: list[NotificationView]


class ReadAllResult(BaseModel):
    updated: int
