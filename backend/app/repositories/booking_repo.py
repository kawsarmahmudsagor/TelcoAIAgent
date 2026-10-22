import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingChannel, BookingStatus
from app.models.client import Client
from app.models.property import Property


def get(db: Session, booking_id: uuid.UUID) -> Booking | None:
    return db.get(Booking, booking_id)


def list_all(
    db: Session, limit: int = 100, offset: int = 0
) -> list[tuple[Booking, str | None, str | None]]:
    """Newest first, as (booking, client full name, client phone)."""
    stmt = (
        select(Booking, Client.full_name, Client.phone)
        .outerjoin(Client, Client.id == Booking.client_id)
        .order_by(Booking.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [tuple(row) for row in db.execute(stmt)]


def create(
    db: Session,
    *,
    client_id: uuid.UUID,
    property_id: uuid.UUID | None,
    channel: BookingChannel,
    proposed_datetime: datetime,
    call_schedule_id: uuid.UUID | None = None,
) -> Booking:
    booking = Booking(
        client_id=client_id,
        property_id=property_id,
        channel=channel,
        proposed_datetime=proposed_datetime,
        call_schedule_id=call_schedule_id,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def count_created_since(db: Session, since: datetime) -> int:
    stmt = select(func.count()).select_from(Booking).where(Booking.created_at >= since)
    return db.scalar(stmt) or 0


def list_recent(db: Session, limit: int = 5) -> list[tuple[Booking, str | None, str | None]]:
    """Newest first, as (booking, client full name, property title)."""
    stmt = (
        select(Booking, Client.full_name, Property.title)
        .outerjoin(Client, Client.id == Booking.client_id)
        .outerjoin(Property, Property.id == Booking.property_id)
        .order_by(Booking.created_at.desc())
        .limit(limit)
    )
    return [tuple(row) for row in db.execute(stmt)]


def next_upcoming_for_client(
    db: Session, client_id: uuid.UUID, after: datetime
) -> tuple[Booking, Property | None] | None:
    """The client's soonest viewing after `after` that isn't cancelled."""
    stmt = (
        select(Booking, Property)
        .outerjoin(Property, Property.id == Booking.property_id)
        .where(
            Booking.client_id == client_id,
            Booking.status != BookingStatus.cancelled,
            Booking.proposed_datetime > after,
        )
        .order_by(Booking.proposed_datetime, Booking.id)
        .limit(1)
    )
    row = db.execute(stmt).first()
    return tuple(row) if row is not None else None


def leads_with_upcoming_viewing(
    db: Session, after: datetime
) -> list[tuple[Client, Booking, Property | None]]:
    """Clients with a viewing after `after` that isn't cancelled, each with
    their soonest one, soonest viewing first."""
    stmt = (
        select(Client, Booking, Property)
        .join(Client, Client.id == Booking.client_id)
        .outerjoin(Property, Property.id == Booking.property_id)
        .where(Booking.status != BookingStatus.cancelled, Booking.proposed_datetime > after)
        .order_by(Booking.proposed_datetime, Booking.id)
    )
    seen: set[uuid.UUID] = set()
    out = []
    for client, booking, prop in db.execute(stmt):
        if client.id not in seen:
            seen.add(client.id)
            out.append((client, booking, prop))
    return out


def upcoming_by_client(
    db: Session, client_ids: set[uuid.UUID], after: datetime
) -> dict[uuid.UUID, list[tuple[Booking, Property | None]]]:
    """Every viewing after `after` that isn't cancelled, for each of
    `client_ids`, soonest first."""
    if not client_ids:
        return {}
    stmt = (
        select(Booking, Property)
        .outerjoin(Property, Property.id == Booking.property_id)
        .where(
            Booking.client_id.in_(client_ids),
            Booking.status != BookingStatus.cancelled,
            Booking.proposed_datetime > after,
        )
        .order_by(Booking.proposed_datetime, Booking.id)
    )
    out: dict[uuid.UUID, list[tuple[Booking, Property | None]]] = {}
    for booking, prop in db.execute(stmt):
        out.setdefault(booking.client_id, []).append((booking, prop))
    return out


def update_time(
    db: Session, booking_id: uuid.UUID, when: datetime
) -> tuple[Booking, datetime] | None:
    """Moves a viewing to `when`. Returns it with its old time, or None if it
    is gone or cancelled."""
    booking = db.get(Booking, booking_id)
    if booking is None or booking.status == BookingStatus.cancelled:
        return None
    old = booking.proposed_datetime
    booking.proposed_datetime = when
    db.commit()
    db.refresh(booking)
    return booking, old


def list_for_client(
    db: Session, client_id: uuid.UUID, *, limit: int = 5
) -> list[tuple[Booking, Property | None]]:
    """The client's viewings that aren't cancelled, latest viewing time first."""
    stmt = (
        select(Booking, Property)
        .outerjoin(Property, Property.id == Booking.property_id)
        .where(Booking.client_id == client_id, Booking.status != BookingStatus.cancelled)
        .order_by(Booking.proposed_datetime.desc())
        .limit(limit)
    )
    return [tuple(row) for row in db.execute(stmt)]
