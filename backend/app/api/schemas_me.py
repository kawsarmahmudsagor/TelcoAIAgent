import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.models.telco import CasePriority, PlanType

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
