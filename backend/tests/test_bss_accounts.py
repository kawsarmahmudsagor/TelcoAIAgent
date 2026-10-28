from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.bss import accounts
from app.bss.errors import InvalidRequest, SubscriberNotFound
from app.bss.types import Allowance
from app.models.telco import UsageKind


def test_summary_totals_and_masking(bss_world, db):
    s = bss_world.subscriber(msisdn="01999002841", main_balance=Decimal("486.50"))
    p = bss_world.package(data_mb=15360, minutes=300, validity_days=30)
    bss_world.subscription(s, p, data_left_mb=8602, minutes_left=182, expires_in_days=3)
    out = accounts.get_account_summary(db, s.id)
    assert out.masked_msisdn == "019••••2841"
    assert out.main_balance == Decimal("486.50")
    assert out.totals == Allowance(data_left_mb=8602, minutes_left=182, sms_left=0)
    assert out.nearest_expiry is not None


def test_summary_ignores_expired_subscriptions(bss_world, db):
    s = bss_world.subscriber()
    p = bss_world.package(data_mb=1024)
    bss_world.subscription(s, p, data_left_mb=500, expires_in_days=-1)
    assert accounts.get_account_summary(db, s.id).totals.data_left_mb == 0


def test_summary_unknown_subscriber(db):
    with pytest.raises(SubscriberNotFound):
        accounts.get_account_summary(db, uuid4())


def test_summary_counts_district_incidents(bss_world, db):
    s = bss_world.subscriber(district="PYTESTVILLE")
    bss_world.incident(district="PYTESTVILLE")
    assert accounts.get_account_summary(db, s.id).district_incidents == 1


def test_usage_breakdown_7_days_daily_series(bss_world, db):
    s = bss_world.subscriber()
    now = datetime.now(timezone.utc)
    for days_ago, mb in ((0, 100), (2, 120), (5, 80), (10, 500)):
        bss_world.usage(s, UsageKind.data, mb, at=now - timedelta(days=days_ago, minutes=1))
    out = accounts.get_usage_breakdown(db, s.id, period_days=7)
    assert len(out.daily) == 7 and sum(v for _, v in out.daily) == Decimal("300")
    assert out.totals[0].amount == Decimal("300")


def test_usage_breakdown_takes_1_to_90_days(bss_world, db):
    s = bss_world.subscriber()
    for days in (1, 3, 14, 90):
        assert accounts.get_usage_breakdown(db, s.id, period_days=days).period_days == days
    for days in (0, 91):
        with pytest.raises(InvalidRequest):
            accounts.get_usage_breakdown(db, s.id, period_days=days)


def test_explain_deductions_only_charged_items(bss_world, db):
    s = bss_world.subscriber()
    bss_world.usage(s, UsageKind.data, 50, charge=0)
    bss_world.usage(s, UsageKind.vas, 1, charge="2.50")
    out = accounts.explain_deductions(db, s.id)
    assert len(out) == 1
    assert out[0].amount == Decimal("2.50") and out[0].source == "usage"


def _incidents(db, district):
    from app.bss import network

    return db.scalars(network.active_incidents_query(district, datetime.now(timezone.utc))).all()


def test_active_incidents_rule(bss_world, db):
    from app.models.telco import IncidentStatus

    now = datetime.now(timezone.utc)
    d = "PYTESTVILLE"
    bss_world.incident(district=d, area="PYTEST resolved", status=IncidentStatus.resolved)
    bss_world.incident(district=d, area="PYTEST ended", ends_at=now - timedelta(minutes=1))
    bss_world.incident(
        district=d, area="PYTEST tomorrow", status=IncidentStatus.scheduled,
        starts_at=now + timedelta(hours=20),
    )
    bss_world.incident(
        district=d, area="PYTEST later", status=IncidentStatus.scheduled,
        starts_at=now + timedelta(days=2),
    )
    bss_world.incident(district=d, area="PYTEST ongoing")
    areas = {i.area for i in _incidents(db, "pytestville")}
    assert areas == {"PYTEST tomorrow", "PYTEST ongoing"}


def test_summary_district_incidents_uses_same_rule(bss_world, db):
    from app.models.telco import IncidentStatus

    s = bss_world.subscriber(district="PYTESTVILLE")
    bss_world.incident(
        district="pytestville", status=IncidentStatus.scheduled,
        starts_at=datetime.now(timezone.utc) + timedelta(hours=20),
    )
    bss_world.incident(
        district="PYTESTVILLE", area="PYTEST later",
        starts_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    assert accounts.get_account_summary(db, s.id).district_incidents == 1
