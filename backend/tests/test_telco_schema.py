"""The telco schema: the migration head matches the models, the real-estate
tables are gone and the reference sequences exist."""

import re
import subprocess

from sqlalchemy import inspect, text


def test_alembic_head_matches_models():
    # `alembic check` exits 0 when models and DB agree
    r = subprocess.run(["uv", "run", "alembic", "check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_real_estate_tables_gone(db):
    names = set(inspect(db.bind).get_table_names())
    assert not names & {
        "properties",
        "clients",
        "bookings",
        "call_schedule",
        "meeting_invites",
        "offer_properties",
    }


def test_ref_sequences_start_values(db):
    # nextval in a rolled-back transaction still advances; only check the format
    ref = db.execute(text("SELECT 'TXN-' || nextval('txn_ref_seq')")).scalar()
    assert re.fullmatch(r"TXN-\d{6,}", ref)
    case_ref = db.execute(text("SELECT 'TC-' || nextval('case_ref_seq')")).scalar()
    assert re.fullmatch(r"TC-\d{4,}", case_ref)
