"""`bss_world`: factories for BSS test data. Rows are committed so code under
test on another session sees them; teardown deletes by reserved prefixes."""

import itertools
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import delete

from app.models.telco import (
    Balance,
    IncidentKind,
    IncidentStatus,
    NetworkIncident,
    Offer,
    Package,
    PackageKind,
    PlanType,
    Subscriber,
    Subscription,
    UsageEvent,
    UsageKind,
)

_counter = itertools.count(random.randint(0, 9000))
_UNITS = {UsageKind.data: "MB", UsageKind.voice: "min", UsageKind.sms: "sms", UsageKind.vas: "item"}


def _next() -> int:
    return next(_counter) % 10000


@dataclass
class BssWorld:
    db: Any

    def subscriber(self, **o: Any) -> Subscriber:
        balance = o.pop("main_balance", Decimal("0"))
        due = o.pop("postpaid_due", Decimal("0"))
        fields: dict[str, Any] = dict(
            msisdn=f"0199900{_next():04d}",
            full_name="PYTEST Subscriber",
            plan_type=PlanType.prepaid,
            district="Dhaka",
            joined_on=date(2024, 1, 1),
        )
        fields.update(o)
        s = Subscriber(**fields)
        self.db.add(s)
        self.db.flush()
        self.db.add(Balance(subscriber_id=s.id, main_balance=balance, postpaid_due=due))
        self.db.commit()
        return s

    def package(self, **o: Any) -> Package:
        fields: dict[str, Any] = dict(
            code=f"PT-{_next():04d}-{random.randint(0, 99999):05d}",
            name="PYTEST Pack",
            kind=PackageKind.bundle,
            data_mb=0,
            minutes=0,
            sms=0,
            validity_days=30,
            price=Decimal("100"),
        )
        fields.update(o)
        p = Package(**fields)
        self.db.add(p)
        self.db.commit()
        return p

    def subscription(self, sub: Subscriber, pkg: Package, **o: Any) -> Subscription:
        now = datetime.now(timezone.utc)
        days = o.pop("expires_in_days", pkg.validity_days)
        fields: dict[str, Any] = dict(
            subscriber_id=sub.id,
            package_id=pkg.id,
            data_left_mb=pkg.data_mb,
            minutes_left=pkg.minutes,
            sms_left=pkg.sms,
            activated_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=days),
        )
        fields.update(o)
        s = Subscription(**fields)
        self.db.add(s)
        self.db.commit()
        return s

    def usage(
        self,
        sub: Subscriber,
        kind: UsageKind,
        amount: Any,
        charge: Any = 0,
        at: datetime | None = None,
        **o: Any,
    ) -> UsageEvent:
        fields: dict[str, Any] = dict(
            subscriber_id=sub.id,
            kind=kind,
            amount=Decimal(str(amount)),
            unit=_UNITS[kind],
            charge=Decimal(str(charge)),
            description=f"PYTEST {kind.value}",
            occurred_at=at or datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        fields.update(o)
        e = UsageEvent(**fields)
        self.db.add(e)
        self.db.commit()
        return e

    def incident(self, **o: Any) -> NetworkIncident:
        fields: dict[str, Any] = dict(
            district="Dhaka",
            area="PYTEST Area",
            kind=IncidentKind.outage,
            status=IncidentStatus.investigating,
            message="PYTEST incident",
            starts_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        fields.update(o)
        i = NetworkIncident(**fields)
        self.db.add(i)
        self.db.commit()
        return i

    def offer(self, **o: Any) -> Offer:
        fields: dict[str, Any] = dict(title=f"PYTEST Offer {_next()}")
        fields.update(o)
        row = Offer(**fields)
        self.db.add(row)
        self.db.commit()
        return row

    def cleanup(self) -> None:
        self.db.rollback()
        self.db.execute(delete(Subscriber).where(Subscriber.msisdn.like("01999%")))
        self.db.execute(delete(Offer).where(Offer.title.like("PYTEST%")))
        self.db.execute(delete(Package).where(Package.code.like("PT-%")))
        self.db.execute(delete(NetworkIncident).where(NetworkIncident.area.like("PYTEST%")))
        self.db.commit()


@pytest.fixture
def bss_world(db):
    world = BssWorld(db)
    world.cleanup()
    try:
        yield world
    finally:
        world.cleanup()
