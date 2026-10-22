import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.meeting_invite import InviteStatus, MeetingInvite, RecipientType


def create(
    db: Session,
    *,
    booking_id: uuid.UUID,
    recipient_type: RecipientType,
    recipient_email: str,
    subject: str,
    body: str,
    sent_status: InviteStatus = InviteStatus.mock_sent,
) -> MeetingInvite:
    invite = MeetingInvite(
        booking_id=booking_id,
        recipient_type=recipient_type,
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        sent_status=sent_status,
        sent_at=datetime.now(timezone.utc),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return invite


def list_for_booking(db: Session, booking_id: uuid.UUID) -> list[MeetingInvite]:
    stmt = select(MeetingInvite).where(MeetingInvite.booking_id == booking_id)
    return list(db.scalars(stmt))
