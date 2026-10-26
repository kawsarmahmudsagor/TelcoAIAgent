"""Customer accounts: self-service signup with a welcome bonus, password checks
and password resets."""

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import bcrypt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.bss import audit
from app.bss.clock import utc_now
from app.bss.errors import MsisdnTaken
from app.config import get_settings
from app.models.telco import (
    Actor,
    Balance,
    Package,
    PackageKind,
    PlanType,
    Subscriber,
    Subscription,
)
from app.services.auth_service import hash_password

WELCOME_BALANCE = Decimal("200")
WELCOME_DATA_MB = 5 * 1024
WELCOME_DAYS = 7
# Not sellable (is_active=False), so it never shows in the catalog.
WELCOME_CODE = "WL-5G-7D"

# Checked against when the number is unknown, so a miss costs as long as a hit.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


def _welcome_package(db: Session) -> Package:
    pkg = db.scalar(select(Package).where(Package.code == WELCOME_CODE))
    if pkg is None:
        pkg = Package(
            code=WELCOME_CODE,
            name="Welcome 5 GB (7 days)",
            kind=PackageKind.data,
            data_mb=WELCOME_DATA_MB,
            minutes=0,
            sms=0,
            validity_days=WELCOME_DAYS,
            price=Decimal("0"),
            is_active=False,
        )
        db.add(pkg)
        db.flush()
    return pkg


def create_subscriber(
    db: Session,
    *,
    full_name: str,
    msisdn: str,
    district: str,
    plan_type: PlanType,
    password: str,
    now: datetime | None = None,
) -> Subscriber:
    """A new active subscriber with ৳200 main balance and a 7-day 5 GB pack. Commits."""
    now = now or utc_now()
    if db.scalar(select(Subscriber.id).where(Subscriber.msisdn == msisdn)) is not None:
        raise MsisdnTaken()
    pkg = _welcome_package(db)
    sub = Subscriber(
        msisdn=msisdn,
        full_name=full_name,
        plan_type=plan_type,
        district=district,
        joined_on=now.astimezone(ZoneInfo(get_settings().agency_timezone)).date(),
        password_hash=hash_password(password),
    )
    db.add(sub)
    try:
        db.flush()
    except IntegrityError:
        # Lost a race with a concurrent signup for the same number.
        db.rollback()
        raise MsisdnTaken()
    db.add(Balance(subscriber_id=sub.id, main_balance=WELCOME_BALANCE))
    db.add(
        Subscription(
            subscriber_id=sub.id,
            package_id=pkg.id,
            data_left_mb=pkg.data_mb,
            minutes_left=pkg.minutes,
            sms_left=pkg.sms,
            activated_at=now,
            expires_at=now + timedelta(days=WELCOME_DAYS),
        )
    )
    audit.record(
        db,
        actor=Actor.portal,
        action="signup",
        subscriber_id=sub.id,
        detail={"plan_type": plan_type.value, "welcome": WELCOME_CODE},
    )
    db.commit()
    return sub


def authenticate(db: Session, msisdn: str, password: str) -> Subscriber | None:
    """The subscriber when the password matches; None for any miss, including a
    subscriber with no password set."""
    sub = db.scalar(select(Subscriber).where(Subscriber.msisdn == msisdn))
    stored = sub.password_hash if sub is not None and sub.password_hash else _DUMMY_HASH
    ok = bcrypt.checkpw(password.encode(), stored.encode())
    return sub if ok and stored is not _DUMMY_HASH else None


def set_password(db: Session, sub: Subscriber, password: str) -> None:
    """Replace the password and audit it. Commits."""
    sub.password_hash = hash_password(password)
    audit.record(db, actor=Actor.portal, action="password_reset", subscriber_id=sub.id)
    db.commit()
