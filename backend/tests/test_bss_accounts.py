from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.bss import accounts
from app.bss.errors import SubscriberNotFound
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


def test_usage_breakdown_rejects_other_periods(bss_world, db):
    s = bss_world.subscriber()
    with pytest.raises(ValueError):
        accounts.get_usage_breakdown(db, s.id, period_days=14)


def test_explain_deductions_only_charged_items(bss_world, db):
    s = bss_world.subscriber()
    bss_world.usage(s, UsageKind.data, 50, charge=0)
    bss_world.usage(s, UsageKind.vas, 1, charge="2.50")
    out = accounts.explain_deductions(db, s.id)
    assert len(out) == 1
    assert out[0].amount == Decimal("2.50") and out[0].source == "usage"
