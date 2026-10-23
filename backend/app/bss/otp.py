"""Simulated OTP challenges bound to (subscriber, action, purpose, request)."""

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bss import audit
from app.bss.clock import utc_now
from app.bss.errors import (
    NoPendingAction,
    OtpAttemptsExceeded,
    OtpExpired,
    OtpInvalid,
    TooManyCodes,
)
from app.models.telco import Actor, OtpChallenge, Subscriber

OTP_TTL = timedelta(minutes=3)
MAX_ATTEMPTS = 3
MAX_CODES_PER_WINDOW = 5
CODE_WINDOW = timedelta(minutes=15)
_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def normalise_code(raw: str) -> str:
    """Bengali digits -> ASCII; everything but digits dropped ('১২৩ ৪৫৬' -> '123456')."""
    return "".join(c for c in raw.translate(_BENGALI_DIGITS) if c in "0123456789")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def request_hash(purpose: str, payload: dict) -> str:
    return _sha256(purpose + json.dumps(payload, sort_keys=True, default=str))


def _code_hash(action_id: uuid.UUID, code: str) -> str:
    return _sha256(f"{action_id}:{code}")


def _get(
    db: Session, subscriber_id: uuid.UUID, action_id: uuid.UUID, *, lock: bool = False
) -> OtpChallenge | None:
    q = select(OtpChallenge).where(
        OtpChallenge.subscriber_id == subscriber_id, OtpChallenge.action_id == action_id
    )
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    return db.scalar(q)


def issued_since(db: Session, subscriber_id: uuid.UUID, since: datetime) -> int:
    """Challenges created at or after `since` (one row per issue when action ids are fresh)."""
    return db.scalar(
        select(func.count())
        .select_from(OtpChallenge)
        .where(OtpChallenge.subscriber_id == subscriber_id, OtpChallenge.created_at >= since)
    )


def issue(
    db: Session,
    *,
    subscriber_id: uuid.UUID,
    action_id: uuid.UUID,
    purpose: str,
    payload: dict,
    now: datetime | None = None,
    actor: Actor = Actor.system,
    throttle: bool = False,
) -> str:
    now = now or utc_now()
    if throttle:
        # Serialise concurrent starts per subscriber so the count below is exact.
        db.execute(select(Subscriber.id).where(Subscriber.id == subscriber_id).with_for_update())
        if issued_since(db, subscriber_id, now - CODE_WINDOW) >= MAX_CODES_PER_WINDOW:
            db.rollback()
            raise TooManyCodes()
    code = f"{secrets.randbelow(10**6):06d}"
    row = _get(db, subscriber_id, action_id)
    if row is not None and row.consumed_at is not None:
        raise OtpInvalid("Action already confirmed")
    if row is not None and row.attempts >= MAX_ATTEMPTS:
        raise OtpAttemptsExceeded()
    if row is None:
        row = OtpChallenge(subscriber_id=subscriber_id, action_id=action_id)
        db.add(row)
    row.purpose = purpose
    row.request_hash = request_hash(purpose, payload)
    row.code_hash = _code_hash(action_id, code)
    row.expires_at = now + OTP_TTL
    row.consumed_at = None
    audit.record(
        db,
        actor=actor,
        action="otp_issue",
        subscriber_id=subscriber_id,
        action_id=action_id,
        detail={"purpose": purpose, "ok": True},
    )
    db.commit()
    return code


def verify(
    db: Session,
    *,
    subscriber_id: uuid.UUID,
    action_id: uuid.UUID,
    purpose: str,
    payload: dict,
    code: str,
    now: datetime | None = None,
    actor: Actor = Actor.system,
) -> None:
    now = now or utc_now()
    row = _get(db, subscriber_id, action_id, lock=True)
    if row is None:
        raise NoPendingAction()
    if row.consumed_at is not None:
        return
    if row.expires_at <= now:
        raise OtpExpired()
    if row.attempts >= MAX_ATTEMPTS:
        raise OtpAttemptsExceeded()
    ok = secrets.compare_digest(row.code_hash, _code_hash(action_id, code)) and (
        row.purpose == purpose and row.request_hash == request_hash(purpose, payload)
    )
    audit.record(
        db,
        actor=actor,
        action="otp_verify",
        subscriber_id=subscriber_id,
        action_id=action_id,
        detail={"purpose": purpose, "ok": ok},
    )
    if not ok:
        row.attempts += 1
        db.commit()
        raise OtpInvalid()
    row.consumed_at = now
    db.commit()


def require_verified(
    db: Session,
    *,
    subscriber_id: uuid.UUID,
    action_id: uuid.UUID,
    purpose: str,
    payload: dict,
    now: datetime | None = None,
) -> None:
    now = now or utc_now()
    row = _get(db, subscriber_id, action_id)
    if (
        row is None
        or row.consumed_at is None
        or row.purpose != purpose
        or row.request_hash != request_hash(purpose, payload)
    ):
        raise OtpInvalid("Action has not been confirmed with a valid code")
    if row.consumed_at + OTP_TTL < now:
        raise OtpExpired()
