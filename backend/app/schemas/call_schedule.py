import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.call_schedule import CallStatus
from app.schemas.client import ClientOut


class CallScheduleCreate(BaseModel):
    client_id: uuid.UUID
    scheduled_at: datetime
    # Phone number to ring; blank/None keeps the browser incoming-call flow.
    # Validated and normalized in the route so errors come back as plain 400s.
    dial_number: str | None = None


class CallScheduleUpdate(BaseModel):
    status: CallStatus | None = None
    scheduled_at: datetime | None = None


class CallScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    scheduled_at: datetime
    status: CallStatus
    dial_number: str | None
    livekit_room_name: str | None
    dispatched_at: datetime | None
    answered_at: datetime | None
    completed_at: datetime | None
    outcome: str | None
    created_at: datetime
    updated_at: datetime


class UpcomingViewingOut(BaseModel):
    booking_id: uuid.UUID
    when: datetime
    property_title: str | None


class ScheduleLeadOut(BaseModel):
    """A lead the agent can call, with their soonest upcoming viewing if any:
    with one the call follows it up, without one it's a plain cold call."""

    client: ClientOut
    viewing: UpcomingViewingOut | None


class CallScheduleWithClientOut(CallScheduleOut):
    client: ClientOut
    # Schedule list only: an open call's lead has this viewing after the call
    # time, so the call will follow it up; None = a cold call (or a closed row).
    viewing: UpcomingViewingOut | None = None


class IncomingCallOut(CallScheduleWithClientOut):
    agent_display_name: str
    agency_name: str


class CallDecline(BaseModel):
    # cancelled: the callee pressed Decline; missed: nobody answered in time.
    reason: Literal["cancelled", "missed"]
