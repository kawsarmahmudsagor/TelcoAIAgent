import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.booking import BookingChannel, BookingStatus
from app.models.meeting_invite import InviteStatus, RecipientType


class MeetingInviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_type: RecipientType
    recipient_email: str
    subject: str
    body: str
    sent_status: InviteStatus
    sent_at: datetime | None


class BookingCreate(BaseModel):
    """A viewing booked by hand on the dashboard for an existing lead."""

    client_id: uuid.UUID
    property_id: uuid.UUID | None = None
    # Without a UTC offset it's read as agency local time.
    proposed_datetime: datetime


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    property_id: uuid.UUID | None
    channel: BookingChannel
    proposed_datetime: datetime
    status: BookingStatus
    call_schedule_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    # From the booking's client; bookings are made with a name and phone number.
    client_name: str | None = None
    client_phone: str | None = None


class BookingDetailOut(BookingOut):
    invites: list[MeetingInviteOut] = []
