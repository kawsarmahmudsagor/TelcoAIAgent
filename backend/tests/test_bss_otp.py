from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.bss import otp
from app.bss.clock import utc_now
from app.bss.errors import NoPendingAction, OtpAttemptsExceeded, OtpExpired, OtpInvalid
from app.models.telco import OtpChallenge

PAYLOAD = {"package_code": "PT-A"}


def _issue(bss_world, db, **o):
    s = bss_world.subscriber()
    action_id = uuid4()
    kw = dict(subscriber_id=s.id, action_id=action_id, purpose="purchase", payload=PAYLOAD)
    kw.update(o)
    return kw, otp.issue(db, **kw)


def test_issue_and_verify_happy_path(bss_world, db):
    kw, code = _issue(bss_world, db)
    assert len(code) == 6 and code.isdigit()
    otp.verify(db, code=code, **kw)
    otp.require_verified(db, **kw)
    otp.verify(db, code="000000", **kw)  # second verify after success is a no-op


def test_wrong_code_counts_attempts_then_locks(bss_world, db):
    kw, code = _issue(bss_world, db)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(3):
        with pytest.raises(OtpInvalid):
            otp.verify(db, code=wrong, **kw)
    with pytest.raises(OtpAttemptsExceeded):
        otp.verify(db, code=code, **kw)


def test_expired_after_three_minutes(bss_world, db):
    kw, code = _issue(bss_world, db)
    with pytest.raises(OtpExpired):
        otp.verify(db, code=code, now=utc_now() + timedelta(seconds=181), **kw)


def test_otp_bound_to_request_hash(bss_world, db):
    kw, code = _issue(bss_world, db)
    kw["payload"] = {"package_code": "PT-B"}
    with pytest.raises(OtpInvalid):
        otp.verify(db, code=code, **kw)


def test_require_verified_without_verify_raises(bss_world, db):
    kw, _ = _issue(bss_world, db)
    with pytest.raises(OtpInvalid):
        otp.require_verified(db, **kw)


def test_code_never_stored_in_plaintext(bss_world, db):
    kw, code = _issue(bss_world, db)
    row = db.scalar(select(OtpChallenge).where(OtpChallenge.action_id == kw["action_id"]))
    assert code not in row.code_hash


def test_verify_unknown_action(bss_world, db):
    s = bss_world.subscriber()
    with pytest.raises(NoPendingAction):
        otp.verify(
            db, subscriber_id=s.id, action_id=uuid4(), purpose="purchase", payload=PAYLOAD, code="123456"
        )


def test_verify_other_subscribers_action_is_no_pending(bss_world, db):
    kw, code = _issue(bss_world, db)
    other = bss_world.subscriber()
    kw["subscriber_id"] = other.id
    with pytest.raises(NoPendingAction):
        otp.verify(db, code=code, **kw)


def test_purpose_mismatch_counts_attempt(bss_world, db):
    kw, code = _issue(bss_world, db)
    kw["purpose"] = "recharge"
    with pytest.raises(OtpInvalid):
        otp.verify(db, code=code, **kw)
    row = db.scalar(select(OtpChallenge).where(OtpChallenge.action_id == kw["action_id"]))
    assert row.attempts == 1


def test_reissue_keeps_attempt_count(bss_world, db):
    kw, code = _issue(bss_world, db)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(2):
        with pytest.raises(OtpInvalid):
            otp.verify(db, code=wrong, **kw)
    new_code = otp.issue(db, **kw)
    row = db.scalar(select(OtpChallenge).where(OtpChallenge.action_id == kw["action_id"]))
    assert row.attempts == 2
    wrong = "000000" if new_code != "000000" else "111111"
    with pytest.raises(OtpInvalid):
        otp.verify(db, code=wrong, **kw)
    with pytest.raises(OtpAttemptsExceeded):
        otp.verify(db, code=new_code, **kw)


def test_require_verified_expires_three_minutes_after_consumption(bss_world, db):
    kw, code = _issue(bss_world, db)
    t0 = utc_now()
    otp.verify(db, code=code, now=t0, **kw)
    otp.require_verified(db, now=t0 + timedelta(minutes=2, seconds=59), **kw)
    with pytest.raises(OtpExpired):
        otp.require_verified(db, now=t0 + timedelta(minutes=3, seconds=1), **kw)
