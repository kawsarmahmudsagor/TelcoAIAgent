from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.telco import Actor, AuditEvent


def record(
    db: Session,
    *,
    actor: Actor,
    action: str,
    subscriber_id: UUID | None,
    action_id: UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Add one audit row; the caller's transaction commits it."""
    db.add(
        AuditEvent(
            actor=actor,
            action=action,
            subscriber_id=subscriber_id,
            action_id=action_id,
            detail=detail or {},
        )
    )
