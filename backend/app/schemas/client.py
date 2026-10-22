import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.client import LeadStatus, RentOrBuy


class ClientBase(BaseModel):
    full_name: str
    phone: str | None = None
    email: str | None = None
    lead_source: str | None = None
    lead_status: LeadStatus = LeadStatus.new
    budget_min: float | None = None
    budget_max: float | None = None
    preferred_location: str | None = None
    preferred_property_type: str | None = None
    bedrooms_wanted: int | None = None
    bathrooms_wanted: float | None = None
    move_in_date: date | None = None
    rent_or_buy: RentOrBuy = RentOrBuy.undecided
    notes: str | None = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    lead_status: LeadStatus | None = None
    notes: str | None = None


class ClientOut(ClientBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
