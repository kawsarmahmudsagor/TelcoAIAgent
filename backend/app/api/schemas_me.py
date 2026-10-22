import uuid

from pydantic import BaseModel

from app.models.telco import PlanType


class PortalMe(BaseModel):
    subscriber_id: uuid.UUID
    full_name: str
    first_name: str
    msisdn: str
    masked_msisdn: str
    plan_type: PlanType
    district: str
