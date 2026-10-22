import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class CallStatus(str, enum.Enum):
    pending = "pending"
    dispatched = "dispatched"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    missed = "missed"


class CallScheduleEntry(TimestampedBase):
    __tablename__ = "call_schedule"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE")
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[CallStatus] = mapped_column(
        Enum(CallStatus, name="call_status"), default=CallStatus.pending
    )

    # E.164 number to ring over the phone network. Set only at creation; None
    # means the call rings the dashboard's browser incoming-call screen instead.
    dial_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    livekit_room_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Set by the agent once someone actually joins the call's room. A call that's
    # in_progress but unanswered is still ringing; once answered it can no longer
    # be declined/missed (see routes_schedule.decline_call).
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
