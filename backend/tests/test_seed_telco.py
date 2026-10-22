from decimal import Decimal

from app.bss import accounts, network
from app.bss.clock import utc_now
from app.data import seed_telco
from app.models.telco import Subscriber


def test_seed_is_idempotent(db):
    seed_telco.seed(db)
    again = seed_telco.seed(db)
    assert set(again.values()) == {0}


def test_samiha_matches_reference_ui(db):
    seed_telco.seed(db)
    s = db.query(Subscriber).filter_by(msisdn="01712342841").one()
    out = accounts.get_account_summary(db, s.id)
    assert out.main_balance == Decimal("486.50") and out.totals.data_left_mb == 8602
    assert out.totals.minutes_left == 182 and out.totals.sms_left == 74
    assert 2 <= (out.nearest_expiry - utc_now()).days <= 3


def test_sylhet_has_active_incident(db):
    seed_telco.seed(db)
    assert network.check_network_status(db, "Sylhet")
