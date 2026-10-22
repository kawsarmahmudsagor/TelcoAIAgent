import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class BookingChannel(str, enum.Enum):
    inbound_chat = "inbound_chat"
    outbound_coldcall = "outbound_coldcall"
    # Added by an admin on the dashboard's bookings page.
    dashboard = "dashboard"


class BookingStatus(str, enum.Enum):
    proposed = "proposed"
    confirmed = "confirmed"
    cancelled = "cancelled"


class Booking(TimestampedBase):
    __tablename__ = "bookings"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE")
    )
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[BookingChannel] = mapped_column(Enum(BookingChannel, name="booking_channel"))
    proposed_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"), default=BookingStatus.proposed
    )
    call_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_schedule.id", ondelete="SET NULL"), nullable=True
    )
