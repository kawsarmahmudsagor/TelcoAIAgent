import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.bss import cases, network
from app.models.telco import (
    Actor,
    AuditEvent,
    CaseSource,
    IncidentKind,
    IncidentStatus,
    Notification,
    NotificationKind,
)


def _case(db, sub, **kw):
    return cases.create_case(
        db,
        sub.id,
        category="billing",
        description="PYTEST case",
        source=kw.pop("source", CaseSource.agent),
        action_id=uuid.uuid4(),
        **kw,
    )


def _notes(db, sub):
    db.expire_all()
    return db.scalars(
        select(Notification).where(
            Notification.subscriber_id == sub.id,
            Notification.kind == NotificationKind.case_update,
        )
    ).all()


def _audits(db, action, **match):
    db.expire_all()
    rows = db.scalars(select(AuditEvent).where(AuditEvent.action == action)).all()
    return [r for r in rows if all(r.detail.get(k) == v for k, v in match.items())]


def test_resolve_case_sets_resolved_at_and_notifies(api, db, bss_world):
    sub = bss_world.subscriber()
    c = _case(db, sub)
    r = api.patch(f"/api/admin/cases/{c.ref}", json={"status": "resolved"})
    assert r.status_code == 200
    assert r.json()["status"] == "resolved" and r.json()["resolved_at"]
    notes = _notes(db, sub)
    assert len(notes) == 1
    assert notes[0].payload == {"case_ref": c.ref, "status": "resolved"}
    audits = _audits(db, "case_status", ref=c.ref)
    assert len(audits) == 1 and audits[0].actor == Actor.admin
    assert audits[0].detail == {"ref": c.ref, "from": "open", "to": "resolved"}


def test_same_status_does_not_renotify(api, db, bss_world):
    sub = bss_world.subscriber()
    c = _case(db, sub)
    for _ in range(2):
        assert api.patch(f"/api/admin/cases/{c.ref}", json={"status": "resolved"}).status_code == 200
    assert len(_notes(db, sub)) == 1
    assert len(_audits(db, "case_status", ref=c.ref)) == 1


def test_reopen_clears_resolved_at(api, db, bss_world):
    sub = bss_world.subscriber()
    c = _case(db, sub)
    api.patch(f"/api/admin/cases/{c.ref}", json={"status": "resolved"})
    r = api.patch(f"/api/admin/cases/{c.ref}", json={"status": "in_review"})
    assert r.json()["status"] == "in_review" and r.json()["resolved_at"] is None


def test_case_ref_normalised_and_unknown_404(api, db, bss_world):
    sub = bss_world.subscriber()
    c = _case(db, sub)
    spaced = c.ref.lower().replace("-", " ")
    assert api.patch(f"/api/admin/cases/{spaced}", json={"status": "in_review"}).status_code == 200
    r = api.patch("/api/admin/cases/TC-1", json={"status": "in_review"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "case_not_found"


def test_cases_list_and_stats(api, db, bss_world):
    sub = bss_world.subscriber(full_name="PYTEST Caser")
    hi = _case(db, sub, priority=cases.CasePriority.high)
    lo = _case(db, sub)
    r = api.get("/api/admin/cases?status=open&limit=100")
    assert r.status_code == 200
    body = r.json()
    refs = [i["ref"] for i in body["items"]]
    assert refs.index(hi.ref) < refs.index(lo.ref)
    item = next(i for i in body["items"] if i["ref"] == hi.ref)
    assert item["subscriber_name"] == "PYTEST Caser" and sub.msisdn not in r.text
    assert api.get("/api/admin/cases?limit=101").status_code == 422
    s = api.get("/api/admin/cases/stats").json()
    assert s["open"] >= 2 and s["high_open"] >= 1
    assert 0 <= s["ai_assisted_share_7d"] <= 1


def test_create_incident_is_seen_by_agent_query(api, db, bss_world):
    sub = bss_world.subscriber(district="PYTESTville")
    r = api.post(
        "/api/admin/network/incidents",
        json={
            "district": "PYTESTville",
            "area": "PYTEST Centre",
            "kind": "outage",
            "status": "investigating",
            "message": "Fibre cut",
        },
    )
    assert r.status_code == 201
    assert r.json()["active"] is True and r.json()["id"]
    seen = network.check_network_status(db, sub.district)
    assert [i.area for i in seen] == ["PYTEST Centre"]
    assert len(_audits(db, "incident_create")) >= 1


def test_incident_end_before_start_422(api):
    start = datetime.now(timezone.utc)
    r = api.post(
        "/api/admin/network/incidents",
        json={
            "district": "Dhaka",
            "area": "PYTEST Area",
            "kind": "outage",
            "status": "investigating",
            "message": "x",
            "starts_at": start.isoformat(),
            "ends_at": (start - timedelta(hours=1)).isoformat(),
        },
    )
    assert r.status_code == 422
    r = api.post(
        "/api/admin/network/incidents",
        json={
            "district": "Dhaka",
            "area": "PYTEST Area",
            "kind": "outage",
            "status": "resolved",
            "message": "x",
        },
    )
    assert r.status_code == 422


def test_resolve_twice_is_noop(api, db, bss_world):
    inc = bss_world.incident()
    first = api.post(f"/api/admin/network/incidents/{inc.id}/resolve")
    assert first.status_code == 200
    assert first.json()["status"] == "resolved" and first.json()["active"] is False
    second = api.post(f"/api/admin/network/incidents/{inc.id}/resolve")
    assert second.status_code == 200
    assert second.json()["ends_at"] == first.json()["ends_at"]
    assert api.post(f"/api/admin/network/incidents/{uuid.uuid4()}/resolve").status_code == 404


def test_district_health(api, db, bss_world):
    now = datetime.now(timezone.utc)
    bss_world.subscriber(district="PYTEST Calm")
    bss_world.incident(district="PYTEST Jam", kind=IncidentKind.congestion)
    bss_world.incident(
        district="PYTEST Plan",
        kind=IncidentKind.maintenance,
        status=IncidentStatus.scheduled,
        starts_at=now + timedelta(days=3),
        ends_at=now + timedelta(days=3, hours=2),
    )
    r = api.get("/api/admin/network")
    assert r.status_code == 200
    health = {d["district"]: d for d in r.json()["districts"]}
    assert health["PYTEST Calm"] == {"district": "PYTEST Calm", "health": "normal", "incidents": 0}
    assert health["PYTEST Jam"]["health"] == "degraded" and health["PYTEST Jam"]["incidents"] == 1
    assert health["PYTEST Plan"]["health"] == "maintenance"
    names = [d["district"] for d in r.json()["districts"]]
    assert names == sorted(names)
    assert {i["district"] for i in r.json()["incidents"]} >= {"PYTEST Jam", "PYTEST Plan"}
