"""Support cases: create (no OTP), human hand-off and status lookup."""

import re
import uuid

from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss import audit
from app.bss.errors import CaseNotFound
from app.bss.types import CaseView
from app.models.telco import (
    Actor,
    CasePriority,
    CaseSource,
    CaseStatus,
    SupportCase,
    case_ref_seq,
)

_ACTOR = {
    CaseSource.agent: Actor.agent,
    CaseSource.portal: Actor.portal,
    CaseSource.admin: Actor.admin,
}


CATEGORY_MAX = 60  # support_cases.category is String(60)


def _normalise_ref(raw: str) -> str:
    """'tc 2048', ' TC-2048 ' and 'TC2048' all mean 'TC-2048'."""
    s = re.sub(r"[\s-]", "", raw).upper()
    return f"TC-{s[2:]}" if s.startswith("TC") else s


def _view(c: SupportCase) -> CaseView:
    return CaseView.model_validate(c)


def _existing(db: Session, subscriber_id: uuid.UUID, action_id: uuid.UUID) -> CaseView | None:
    row = db.scalar(select(SupportCase).where(SupportCase.action_id == action_id))
    if row is None:
        return None
    if row.subscriber_id != subscriber_id:
        # Cases have no OTP, so never hand back another subscriber's case.
        raise CaseNotFound()
    return _view(row)


def create_case(
    db: Session,
    subscriber_id: uuid.UUID,
    *,
    category: str,
    description: str,
    priority: CasePriority = CasePriority.normal,
    source: CaseSource,
    action_id: uuid.UUID,
) -> CaseView:
    if len(category) > CATEGORY_MAX:
        raise ValueError(f"category must be at most {CATEGORY_MAX} characters")
    found = _existing(db, subscriber_id, action_id)
    if found is not None:
        return found
    ref = f"TC-{db.scalar(case_ref_seq.next_value())}"
    row = SupportCase(
        ref=ref,
        subscriber_id=subscriber_id,
        action_id=action_id,
        category=category,
        description=description,
        priority=priority,
        status=CaseStatus.open,
        source=source,
    )
    db.add(row)
    audit.record(
        db,
        actor=_ACTOR[source],
        action="case_created",
        subscriber_id=subscriber_id,
        action_id=action_id,
        detail={"ref": ref, "category": category, "priority": priority.value},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        found = _existing(db, subscriber_id, action_id)
        if found is None:
            raise
        return found
    return _view(row)


def request_human_agent(
    db: Session,
    subscriber_id: uuid.UUID,
    *,
    reason: str,
    source: CaseSource,
    action_id: uuid.UUID,
) -> CaseView:
    return create_case(
        db,
        subscriber_id,
        category="human_handoff",
        description=reason,
        priority=CasePriority.high,
        source=source,
        action_id=action_id,
    )


def get_case_status(
    db: Session, subscriber_id: uuid.UUID, *, ref: str | None = None, limit: int = 5
) -> list[CaseView]:
    q = select(SupportCase).where(SupportCase.subscriber_id == subscriber_id)
    if ref is not None:
        row = db.scalar(q.where(SupportCase.ref == _normalise_ref(ref)))
        if row is None:
            raise CaseNotFound()
        return [_view(row)]
    rows = db.scalars(
        q.order_by(
            case((SupportCase.status == CaseStatus.resolved, 1), else_=0),
            SupportCase.created_at.desc(),
        ).limit(limit)
    ).all()
    return [_view(r) for r in rows]
