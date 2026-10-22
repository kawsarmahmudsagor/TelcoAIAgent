import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_db
from app.agent.tools._datetime import agency_tz, viewing_hours_text, within_viewing_hours
from app.config import get_settings
from app.models.booking import BookingChannel
from app.repositories import booking_repo, client_repo, invite_repo, property_repo
from app.schemas.booking import BookingCreate, BookingDetailOut, BookingOut
from app.services import mock_email_service

router = APIRouter(
    prefix="/api/bookings", tags=["bookings"], dependencies=[Depends(get_current_admin)]
)


@router.get("", response_model=list[BookingOut])
def list_bookings(db: Session = Depends(get_db), limit: int = 100, offset: int = 0) -> list:
    return [
        BookingOut.model_validate(booking).model_copy(
            update={"client_name": client_name, "client_phone": client_phone}
        )
        for booking, client_name, client_phone in booking_repo.list_all(
            db, limit=limit, offset=offset
        )
    ]


@router.post("", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)):
    """Books a viewing by hand for an existing lead, held to the same rules as
    the agent's bookings: a future time inside viewing hours, an active listing.
    A call scheduled for the lead before it then follows it up."""
    client = client_repo.get(db, payload.client_id)
    if not client:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    prop = None
    if payload.property_id is not None:
        prop = property_repo.get_active(db, payload.property_id)
        if prop is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
    when = payload.proposed_datetime
    if when.tzinfo is None:
        when = when.replace(tzinfo=agency_tz())
    if when <= datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The viewing time is in the past")
    if not within_viewing_hours(when):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Viewings run from {viewing_hours_text()}"
        )
    booking = booking_repo.create(
        db,
        client_id=client.id,
        property_id=prop.id if prop is not None else None,
        channel=BookingChannel.dashboard,
        proposed_datetime=when,
    )
    mock_email_service.send_invite(
        db,
        booking_id=booking.id,
        client_name=client.full_name,
        client_email=client.email,
        client_phone=client.phone,
        ceo_email=get_settings().ceo_email,
        property_title=prop.title if prop is not None else None,
        when=when,
    )
    return BookingOut.model_validate(booking).model_copy(
        update={"client_name": client.full_name, "client_phone": client.phone}
    )


@router.get("/{booking_id}", response_model=BookingDetailOut)
def get_booking(booking_id: uuid.UUID, db: Session = Depends(get_db)):
    booking = booking_repo.get(db, booking_id)
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    invites = invite_repo.list_for_booking(db, booking_id)
    client = client_repo.get(db, booking.client_id)
    fields = BookingOut.model_validate(booking).model_dump()
    fields.update(
        client_name=client.full_name if client else None,
        client_phone=client.phone if client else None,
    )
    return BookingDetailOut(**fields, invites=invites)
