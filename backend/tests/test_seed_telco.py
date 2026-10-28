"""The telco demo seed. Every test reseeds inside the rolled-back `db` session
(after clearing the live demo rows there), so assertions are relative to a fixed
`now` and never depend on how stale or used the dev database's demo data is."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.bss import accounts, network
from app.data import seed_telco
from app.models.telco import (
    Balance,
    NetworkIncident,
    Offer,
    Package,
    Subscriber,
    Subscription,
    Transaction,
    TxnType,
)

FIXED_NOW = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)
SAMIHA = "01712342841"


def _fresh(db) -> dict[str, int]:
    """Clear the demo rows and seed again at FIXED_NOW, without committing."""
    return seed_telco.reset(db, now=FIXED_NOW)


def _samiha(db) -> Subscriber:
    return db.scalars(select(Subscriber).where(Subscriber.msisdn == SAMIHA)).one()


def test_seed_is_idempotent(db):
    first = _fresh(db)
    assert first["subscribers"] == 5 and first["incidents"] == 2 and first["offers"] == len(seed_telco.OFFERS)
    again = seed_telco.seed(db, now=FIXED_NOW)
    assert set(again.values()) == {0}


def test_samiha_matches_reference_ui(db):
    _fresh(db)
    out = accounts.get_account_summary(db, _samiha(db).id, now=FIXED_NOW)
    assert out.main_balance == Decimal("486.50") and out.totals.data_left_mb == 8602
    assert out.totals.minutes_left == 182 and out.totals.sms_left == 74
    assert out.nearest_expiry - FIXED_NOW == timedelta(days=3)


def test_samiha_pack_purchase_dated_at_activation(db):
    _fresh(db)
    s = _samiha(db)
    pkg = db.scalars(select(Package).where(Package.code == "B15-300")).one()
    sub = db.scalars(
        select(Subscription).where(
            Subscription.subscriber_id == s.id, Subscription.package_id == pkg.id
        )
    ).one()
    txn = db.scalars(
        select(Transaction).where(
            Transaction.subscriber_id == s.id,
            Transaction.type == TxnType.purchase,
            Transaction.package_id == pkg.id,
        )
    ).one()
    assert txn.created_at == sub.activated_at == FIXED_NOW - timedelta(days=27)


def test_sylhet_has_active_incident(db):
    _fresh(db)
    assert network.check_network_status(db, "Sylhet", now=FIXED_NOW)


def test_reset_restores_demo_rows_and_keeps_test_rows(bss_world, db):
    keep = bss_world.subscriber()
    _fresh(db)
    # Demo use drifts the data: Samiha spends money, someone seeds twice.
    db.get(Balance, _samiha(db).id).main_balance = Decimal("1.00")
    db.flush()
    counts = _fresh(db)
    assert counts["subscribers"] == 5
    assert db.get(Balance, _samiha(db).id).main_balance == Decimal("486.50")
    assert db.get(Subscriber, keep.id) is not None
    demo = ~Subscriber.msisdn.like("01999%")
    assert db.scalar(select(func.count()).select_from(Subscriber).where(demo)) == 5
    titles = [o.title for o in db.scalars(select(Offer)) if not o.title.startswith("PYTEST")]
    assert sorted(titles) == sorted(seed_telco.OFFER_TITLES)
    areas = [
        i.area
        for i in db.scalars(select(NetworkIncident))
        if i.area in {"Sylhet Sadar", "Gazipur Sadar"}
    ]
    assert sorted(areas) == ["Gazipur Sadar", "Sylhet Sadar"]
    codes = db.scalars(select(Package.code).where(Package.code.in_(seed_telco.PACKAGE_CODES)))
    assert sorted(codes) == sorted(seed_telco.PACKAGE_CODES)
