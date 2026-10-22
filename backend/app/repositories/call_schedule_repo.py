import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.call_schedule import CallScheduleEntry, CallStatus


def get(db: Session, entry_id: uuid.UUID) -> CallScheduleEntry | None:
    return db.get(CallScheduleEntry, entry_id)


def list_all(
    db: Session, *, status: CallStatus | None = None, limit: int = 100, offset: int = 0
) -> list[CallScheduleEntry]:
    stmt = select(CallScheduleEntry).order_by(CallScheduleEntry.scheduled_at.asc())
    if status is not None:
        stmt = stmt.where(CallScheduleEntry.status == status)
    stmt = stmt.limit(limit).offset(offset)
    return list(db.scalars(stmt))


def create(
    db: Session, *, client_id: uuid.UUID, scheduled_at: datetime, dial_number: str | None = None
) -> CallScheduleEntry:
    entry = CallScheduleEntry(client_id=client_id, scheduled_at=scheduled_at, dial_number=dial_number)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def update_fields(db: Session, entry: CallScheduleEntry, data: dict) -> CallScheduleEntry:
    for key, value in data.items():
        if value is not None:
            setattr(entry, key, value)
    db.commit()
    db.refresh(entry)
    return entry


def transition(
    db: Session,
    entry_id: uuid.UUID,
    *,
    from_statuses: set[CallStatus],
    values: dict,
    unanswered_only: bool = False,
) -> bool:
    """Atomically applies `values` only if the row's status is still one of
    `from_statuses` (and, with `unanswered_only`, nobody has answered it yet),
    in a single UPDATE. Returns whether a row changed. Use this instead of
    update_fields when several writers (scheduler, decline endpoint, agent) can
    race on the same call, so a late writer can't clobber an already-terminal
    status like cancelled/missed, or end a call that's already been answered."""
    conditions = [CallScheduleEntry.id == entry_id, CallScheduleEntry.status.in_(from_statuses)]
    if unanswered_only:
        conditions.append(CallScheduleEntry.answered_at.is_(None))
    stmt = (
        update(CallScheduleEntry)
        .where(*conditions)
        .values(**values)
        .returning(CallScheduleEntry.id)
    )
    changed = db.scalars(stmt).first() is not None
    db.commit()
    return changed


def delete(db: Session, entry: CallScheduleEntry) -> None:
    db.delete(entry)
    db.commit()


def claim_due_entries(db: Session, *, limit: int = 5) -> list[CallScheduleEntry]:
    """Atomically claim up to `limit` due, pending entries by flipping them to
    'dispatched' in a single UPDATE ... RETURNING, so two scheduler instances
    (or a restarted one) never dispatch the same call twice."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(CallScheduleEntry)
        .where(
            CallScheduleEntry.status == CallStatus.pending,
            CallScheduleEntry.scheduled_at <= now,
            CallScheduleEntry.id.in_(
                select(CallScheduleEntry.id)
                .where(
                    CallScheduleEntry.status == CallStatus.pending,
                    CallScheduleEntry.scheduled_at <= now,
                )
                .order_by(CallScheduleEntry.scheduled_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            ),
        )
        .values(status=CallStatus.dispatched, dispatched_at=now)
        .returning(CallScheduleEntry.id)
    )
    claimed_ids = list(db.scalars(stmt))
    db.commit()
    if not claimed_ids:
        return []
    return list(db.scalars(select(CallScheduleEntry).where(CallScheduleEntry.id.in_(claimed_ids))))
