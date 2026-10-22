import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class RecipientType(str, enum.Enum):
    client = "client"
    ceo = "ceo"


class InviteStatus(str, enum.Enum):
    mock_sent = "mock_sent"
    failed = "failed"


class MeetingInvite(TimestampedBase):
    __tablename__ = "meeting_invites"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE")
    )
    recipient_type: Mapped[RecipientType] = mapped_column(
        Enum(RecipientType, name="recipient_type")
    )
    recipient_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    sent_status: Mapped[InviteStatus] = mapped_column(
        Enum(InviteStatus, name="invite_status"), default=InviteStatus.mock_sent
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
