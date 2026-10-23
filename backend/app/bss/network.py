import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.bss import audit
from app.bss.clock import utc_now
from app.bss.errors import IncidentNotFound, InvalidRequest
from app.bss.types import IncidentView
from app.models.telco import Actor, IncidentKind, IncidentStatus, NetworkIncident


class IncidentAdminView(IncidentView):
    id: uuid.UUID
    active: bool


def is_active(row: NetworkIncident, now: datetime) -> bool:
    """`active_incidents_query`'s rule, for one row in Python."""
    return (
        row.status != IncidentStatus.resolved
        and row.starts_at <= now + timedelta(days=1)
        and (row.ends_at is None or row.ends_at > now)
    )


def admin_view(row: NetworkIncident, now: datetime) -> IncidentAdminView:
    return IncidentAdminView(
        **IncidentView.model_validate(row).model_dump(), id=row.id, active=is_active(row, now)
    )


def active_incidents_query(district: str, now: datetime) -> Select:
    """Incidents in force in `district` at `now`: not resolved, starting within
    the next day (so scheduled maintenance tomorrow shows), not yet ended.
    The one rule shared by account summaries and the network status check."""
    return select(NetworkIncident).where(
        func.lower(NetworkIncident.district) == district.lower(),
        NetworkIncident.status != IncidentStatus.resolved,
        NetworkIncident.starts_at <= now + timedelta(days=1),
        (NetworkIncident.ends_at.is_(None)) | (NetworkIncident.ends_at > now),
    )


def check_network_status(
    db: Session, district: str, *, now: datetime | None = None
) -> list[IncidentView]:
    rows = db.scalars(
        active_incidents_query(district, now or utc_now()).order_by(
            NetworkIncident.starts_at.asc(), NetworkIncident.area.asc()
        )
    ).all()
    return [IncidentView.model_validate(r) for r in rows]


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def create_incident(
    db: Session,
    *,
    district: str,
    area: str,
    kind: IncidentKind,
    status: IncidentStatus,
    message: str,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> IncidentAdminView:
    if status not in (IncidentStatus.investigating, IncidentStatus.scheduled):
        raise InvalidRequest("status must be investigating or scheduled")
    now = utc_now()
    starts_at = _aware(starts_at) or now
    ends_at = _aware(ends_at)
    if ends_at is not None and ends_at <= starts_at:
        raise InvalidRequest("ends_at must be after starts_at")
    row = NetworkIncident(
        district=district,
        area=area,
        kind=kind,
        status=status,
        message=message,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        actor=Actor.admin,
        action="incident_create",
        subscriber_id=None,
        detail={
            "id": str(row.id),
            "district": district,
            "area": area,
            "kind": kind.value,
            "status": status.value,
        },
    )
    db.commit()
    return admin_view(row, now)


def resolve_incident(db: Session, incident_id: uuid.UUID) -> IncidentAdminView:
    row = db.get(NetworkIncident, incident_id)
    if row is None:
        raise IncidentNotFound()
    now = utc_now()
    if row.status != IncidentStatus.resolved:
        row.status = IncidentStatus.resolved
        if row.ends_at is None or row.ends_at > now:
            row.ends_at = now
        audit.record(
            db,
            actor=Actor.admin,
            action="incident_resolve",
            subscriber_id=None,
            detail={"id": str(row.id), "district": row.district, "area": row.area},
        )
        db.commit()
    return admin_view(row, now)
