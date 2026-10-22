import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.bss import cases, network
from app.bss.errors import CaseNotFound
from app.models.telco import (
    CasePriority,
    CaseSource,
    CaseStatus,
    IncidentStatus,
    SupportCase,
)


def _mk(db, s, aid=None):
    return cases.create_case(
        db,
        s.id,
        category="billing",
        description="PYTEST case",
        source=CaseSource.agent,
        action_id=aid or uuid4(),
    )


def test_create_case_ref_and_idempotency(bss_world, db):
    s = bss_world.subscriber()
    aid = uuid4()
    a = _mk(db, s, aid)
    b = _mk(db, s, aid)
    assert re.fullmatch(r"TC-\d+", a.ref) and a.ref == b.ref
    assert a.status == CaseStatus.open and a.priority == CasePriority.normal
    n = db.scalar(select(func.count()).select_from(SupportCase).where(SupportCase.action_id == aid))
    assert n == 1


def test_create_case_replay_from_other_subscriber_rejected(bss_world, db):
    s1, s2 = bss_world.subscriber(), bss_world.subscriber()
    aid = uuid4()
    _mk(db, s1, aid)
    with pytest.raises(CaseNotFound):
        _mk(db, s2, aid)


def test_human_handoff_is_high_priority(bss_world, db):
    s = bss_world.subscriber()
    c = cases.request_human_agent(
        db, s.id, reason="wants a person", source=CaseSource.agent, action_id=uuid4()
    )
    assert c.category == "human_handoff" and c.priority == CasePriority.high
    assert c.description == "wants a person"


def test_case_status_scoped_to_subscriber(bss_world, db):
    s1, s2 = bss_world.subscriber(), bss_world.subscriber()
    c = _mk(db, s1)
    assert cases.get_case_status(db, s1.id, ref=c.ref)[0].ref == c.ref
    with pytest.raises(CaseNotFound):
        cases.get_case_status(db, s2.id, ref=c.ref)
    with pytest.raises(CaseNotFound):
        cases.get_case_status(db, s1.id, ref="TC-0")
    assert cases.get_case_status(db, s2.id) == []


def test_case_status_unresolved_first(bss_world, db):
    s = bss_world.subscriber()
    old_open = _mk(db, s)
    resolved = _mk(db, s)
    new_open = _mk(db, s)
    row = db.scalar(select(SupportCase).where(SupportCase.ref == resolved.ref))
    row.status = CaseStatus.resolved
    row.resolved_at = datetime.now(timezone.utc)
    db.commit()
    got = [c.ref for c in cases.get_case_status(db, s.id)]
    assert got == [new_open.ref, old_open.ref, resolved.ref]
    assert len(cases.get_case_status(db, s.id, limit=2)) == 2


def _areas(res):
    return {i.area for i in res if i.area.startswith("PYTEST")}


def test_network_status_ignores_resolved_and_ended(bss_world, db):
    now = datetime.now(timezone.utc)
    bss_world.incident(area="PYTEST live", district="Sylhet")
    bss_world.incident(area="PYTEST resolved", district="Sylhet", status=IncidentStatus.resolved)
    bss_world.incident(area="PYTEST ended", district="Sylhet", ends_at=now - timedelta(minutes=1))
    bss_world.incident(area="PYTEST other", district="Gazipur")
    res = network.check_network_status(db, "sYLHET", now=now)
    assert _areas(res) == {"PYTEST live"}


def test_network_status_includes_maintenance_within_a_day(bss_world, db):
    now = datetime.now(timezone.utc)
    bss_world.incident(
        area="PYTEST tomorrow",
        district="Sylhet",
        status=IncidentStatus.scheduled,
        starts_at=now + timedelta(hours=23),
    )
    bss_world.incident(
        area="PYTEST later",
        district="Sylhet",
        status=IncidentStatus.scheduled,
        starts_at=now + timedelta(days=2),
    )
    assert _areas(network.check_network_status(db, "Sylhet", now=now)) == {"PYTEST tomorrow"}
