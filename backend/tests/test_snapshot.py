"""load_session_context: the per-session account snapshot, first name and nudge
wording, built from bss reads (real Postgres via bss_world)."""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.agent.snapshot import GUEST_SNAPSHOT, load_session_context
from app.agent.telco_format import format_day
from app.models.telco import (
    IncidentKind,
    IncidentStatus,
    Notification,
    NotificationKind,
    PackageKind,
    PlanType,
)
from word_checks import real_estate_words


@pytest.fixture
def notify(bss_world):
    """Adds a notifications row (deleted with its subscriber by cleanup)."""

    def add(sub, kind: NotificationKind, payload: dict) -> Notification:
        row = Notification(
            subscriber_id=sub.id, kind=kind, subject_key=f"pytest-{uuid.uuid4()}", payload=payload
        )
        bss_world.db.add(row)
        bss_world.db.commit()
        return row

    return add


def test_snapshot_survives_network_failure(bss_world, monkeypatch):
    from app.bss import network

    def boom(*a, **k):
        raise RuntimeError("network lookup down")

    monkeypatch.setattr(network, "check_network_status", boom)
    sub = bss_world.subscriber(full_name="Samiha Khan")
    ctx = load_session_context(sub.id, None)
    assert ctx.subscriber_id == sub.id and ctx.customer_name == "Samiha Khan"
    assert "Network status in" in ctx.snapshot and "unavailable" in ctx.snapshot


def test_snapshot_for_prepaid_persona(bss_world):
    sub = bss_world.subscriber(full_name="Samiha Khan", main_balance=Decimal("486.50"))
    pkg = bss_world.package(name="PYTEST Net 15", kind=PackageKind.data, data_mb=15360, minutes=0)
    subscription = bss_world.subscription(sub, pkg, expires_in_days=3)
    bss_world.incident(area="PYTEST Mirpur 10", kind=IncidentKind.congestion)

    ctx = load_session_context(sub.id, None)

    assert ctx.subscriber_id == sub.id
    assert ctx.customer_name == "Samiha Khan"
    assert ctx.nudge_text is None
    text = ctx.snapshot
    assert "sample" in text.lower()
    assert "Samiha Khan" in text
    assert f"{sub.msisdn[:3]}••••{sub.msisdn[-4:]}" in text
    assert sub.msisdn not in text
    assert "prepaid" in text
    assert "486.50 taka" in text
    assert "PYTEST Net 15" in text and "15 GB" in text
    assert format_day(subscription.expires_at) in text
    assert "PYTEST Mirpur 10" in text and "congestion" in text and "investigating" in text
    assert "Bill due" not in text
    assert "Care centres in their district (Dhaka)" in text
    assert real_estate_words(text) == []


def test_snapshot_for_postpaid_shows_due(bss_world):
    sub = bss_world.subscriber(
        full_name="Nusrat Mahmud",
        plan_type=PlanType.postpaid,
        district="PYTEST-Nowhere",
        postpaid_due=Decimal("1240"),
    )

    ctx = load_session_context(sub.id, None)

    assert "Bill due: 1,240 taka" in ctx.snapshot
    assert "Main balance" not in ctx.snapshot
    assert "No active packs" in ctx.snapshot
    assert "No network incidents" in ctx.snapshot
    assert "care centre" not in ctx.snapshot.lower()  # district not one we know


def test_snapshot_names_the_nearest_care_centre(bss_world):
    sub = bss_world.subscriber(district="Gazipur")
    snapshot = load_session_context(sub.id, None).snapshot
    assert "Nearest care centre to their district: Uttara care centre" in snapshot


def test_unknown_subscriber_becomes_guest():
    for sid in (uuid.uuid4(), None):
        ctx = load_session_context(sid, uuid.uuid4())
        assert ctx.subscriber_id is None
        assert ctx.customer_name is None
        assert ctx.snapshot == GUEST_SNAPSHOT
        assert ctx.nudge_text is None


def test_nudge_text_only_for_own_notification(bss_world, notify):
    sub = bss_world.subscriber(full_name="Rafiul Hasan")
    other = bss_world.subscriber(full_name="Someone Else")
    expires = datetime.now(timezone.utc) + timedelta(days=2)
    own = notify(
        sub,
        NotificationKind.pack_expiring,
        {"package_name": "PYTEST Net 15", "expires_at": expires.isoformat()},
    )
    foreign = notify(other, NotificationKind.low_balance, {"balance": "12.00"})

    text = load_session_context(sub.id, own.id).nudge_text
    assert text is not None
    assert "PYTEST Net 15" in text and format_day(expires) in text

    assert load_session_context(sub.id, foreign.id).nudge_text is None
    assert load_session_context(sub.id, uuid.uuid4()).nudge_text is None


def test_nudge_text_for_each_kind(bss_world, notify):
    sub = bss_world.subscriber()
    cases = {
        NotificationKind.low_balance: ({"balance": "42"}, "42 taka"),
        NotificationKind.low_data: (
            {"package_name": "PYTEST Net 15", "data_left_mb": 800},
            "800 MB",
        ),
        NotificationKind.case_update: ({"case_ref": "TC-2051", "status": "resolved"}, "TC-2051"),
        # A payload missing its fields still gives a usable line.
        NotificationKind.pack_expiring: ({}, "pack"),
    }
    for kind, (payload, expected) in cases.items():
        row = notify(sub, kind, payload)
        text = load_session_context(sub.id, row.id).nudge_text
        assert text and expected in text, kind
