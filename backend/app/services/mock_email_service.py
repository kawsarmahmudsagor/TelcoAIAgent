"""Stand-in for a real calendar/SMTP integration.

Logs a meeting invite to the `meeting_invites` table (and stdout) instead of
actually sending email or creating a calendar event. Swap this out for a real
Google Calendar / SMTP implementation later without touching callers, since
they only depend on `send_invite`'s signature.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.meeting_invite import MeetingInvite, RecipientType
from app.repositories import invite_repo


def _build_body(
    *,
    client_name: str,
    client_phone: str | None,
    property_title: str | None,
    when: datetime,
    rescheduled_from: datetime | None = None,
) -> str:
    where = f" for {property_title}" if property_title else ""
    phone = f" (phone {client_phone})" if client_phone else ""
    moved = f" Rescheduled from {rescheduled_from.isoformat()}." if rescheduled_from else ""
    return (
        f"Viewing appointment{where} confirmed with {client_name}{phone} "
        f"at {when.isoformat()}.{moved} (mock invite — no real calendar/email sent yet)"
    )


def send_invite(
    db: Session,
    *,
    booking_id: uuid.UUID,
    client_name: str,
    client_email: str | None,
    ceo_email: str,
    property_title: str | None,
    when: datetime,
    client_phone: str | None = None,
    rescheduled_from: datetime | None = None,
) -> list[MeetingInvite]:
    """The agency (CEO) is always invited. The customer only when an email is on
    file: bookings are made with a name and phone number, so most have none.
    `rescheduled_from`: the old time of a viewing that was moved."""
    kind = "Viewing rescheduled" if rescheduled_from else "Viewing appointment"
    subject = f"{kind}: {client_name}" + (f" — {property_title}" if property_title else "")
    body = _build_body(
        client_name=client_name,
        client_phone=client_phone,
        property_title=property_title,
        when=when,
        rescheduled_from=rescheduled_from,
    )

    recipients = [(RecipientType.ceo, ceo_email)]
    if client_email:
        recipients.insert(0, (RecipientType.client, client_email))
    invites = [
        invite_repo.create(
            db,
            booking_id=booking_id,
            recipient_type=recipient_type,
            recipient_email=email,
            subject=subject,
            body=body,
        )
        for recipient_type, email in recipients
    ]
    for invite in invites:
        print(f"[mock_email_service] invite mock-sent to {invite.recipient_email}: {subject}")
    return invites
