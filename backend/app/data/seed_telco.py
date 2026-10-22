"""Demo data for the telco assistant: packages, five personas with balances,
subscriptions, 30 days of usage, transactions and cases, two network incidents
and three offers. Written straight through the ORM (history, not replayed into
balances)."""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bss._txn import next_ref
from app.config import get_settings
from app.models.telco import (
    Balance,
    CasePriority,
    CaseSource,
    CaseStatus,
    IncidentKind,
    IncidentStatus,
    NetworkIncident,
    Offer,
    OfferAudience,
    Package,
    PackageKind,
    PlanType,
    Subscriber,
    Subscription,
    SubscriptionStatus,
    SupportCase,
    Transaction,
    TxnChannel,
    TxnStatus,
    TxnType,
    UsageEvent,
    UsageKind,
    case_ref_seq,
)

D = Decimal

# code, name, kind, data_mb, minutes, sms, days, price, tag
PACKAGES = [
    ("D1-1D", "1 GB Daily", "data", 1024, 0, 0, 1, 29, None),
    ("D3-3D", "3 GB Weekend", "data", 3072, 0, 0, 3, 69, "WEEKEND"),
    ("D8-7D", "8 GB Weekly", "data", 8192, 0, 0, 7, 149, "BEST VALUE"),
    ("D15-30D", "15 GB Monthly", "data", 15360, 0, 0, 30, 349, None),
    ("D30-30D", "30 GB Monthly", "data", 30720, 0, 0, 30, 549, None),
    ("D50-30D", "50 GB Monthly", "data", 51200, 0, 0, 30, 749, None),
    ("V100-7D", "100 Minutes", "voice", 0, 100, 0, 7, 79, "SHORT CALLS"),
    ("V300-30D", "300 Minutes", "voice", 0, 300, 0, 30, 199, "VOICE"),
    ("V600-30D", "600 Minutes", "voice", 0, 600, 0, 30, 349, None),
    ("B5-100", "5 GB + 100 min", "bundle", 5120, 100, 0, 7, 179, None),
    ("B15-300", "Smart 15 GB + 300 min", "bundle", 15360, 300, 0, 30, 399, "POPULAR"),
    ("B20-200", "20 GB + 200 min", "bundle", 20480, 200, 0, 30, 449, "EXCLUSIVE"),
    ("B40-500", "40 GB + 500 min", "bundle", 40960, 500, 0, 30, 799, None),
    ("S100-30D", "100 SMS", "sms", 0, 0, 100, 30, 29, None),
    ("S500-30D", "500 SMS", "sms", 0, 0, 500, 30, 79, None),
]

# msisdn, name, plan, district, joined_on, balance, due, points, daily data MB range
PERSONAS = [
    ("01712342841", "Samiha Khan", "prepaid", "Dhaka", date(2024, 3, 14), "486.50", "0", 840, (150, 350)),
    ("01812347392", "Rafi Ahmed", "prepaid", "Chattogram", date(2023, 9, 2), "42.00", "0", 120, (300, 600)),
    ("01912345501", "Nusrat Mahmud", "postpaid", "Rajshahi", date(2022, 6, 21), "0", "1240.00", 300, (600, 1200)),
    ("01612341109", "Tanvir Hasan", "prepaid", "Sylhet", date(2024, 11, 5), "215.00", "0", 60, (200, 500)),
    ("01512346620", "Farhana Islam", "prepaid", "Gazipur", date(2021, 12, 9), "730.25", "0", 2150, (250, 450)),
]

# msisdn -> [(package code, data_left, minutes_left, sms_left, expires in days)]
SUBSCRIPTIONS = {
    "01712342841": [("B15-300", 8602, 182, 0, 3), ("S100-30D", 0, 0, 74, 20)],
    "01812347392": [("D8-7D", 2100, 0, 0, 5)],
    "01912345501": [("B40-500", 30000, 410, 0, 18)],
    "01612341109": [("D15-30D", 1200, 0, 0, 11)],
    "01512346620": [("B20-200", 12000, 150, 0, 20)],
}

VAS = [
    ("Caller tune renewal", D("5.00")),
    ("News alert subscription", D("2.50")),
    ("Caller tune renewal", D("10.00")),
]


def _local_dt(day: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, t, tzinfo=tz)


def _rand_time(rng: random.Random) -> time:
    return time(rng.randint(8, 22), rng.randint(0, 59))


def seed(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    counts = dict.fromkeys(
        [
            "subscribers",
            "packages",
            "subscriptions",
            "usage_events",
            "transactions",
            "cases",
            "incidents",
            "offers",
        ],
        0,
    )
    existing = db.scalar(
        select(func.count()).select_from(Subscriber).where(~Subscriber.msisdn.like("01999%"))
    )
    if existing:
        return counts

    tz = ZoneInfo(get_settings().agency_timezone)
    now = (now or datetime.now(tz)).astimezone(tz)
    today = now.date()
    rng = random.Random(2026)

    pkgs: dict[str, Package] = {}
    for code, name, kind, mb, mins, sms, days, price, tag in PACKAGES:
        pkg = db.scalar(select(Package).where(Package.code == code))
        if pkg is None:
            pkg = Package(
                code=code,
                name=name,
                kind=PackageKind(kind),
                data_mb=mb,
                minutes=mins,
                sms=sms,
                validity_days=days,
                price=D(price),
                is_active=True,
                tag=tag,
            )
            db.add(pkg)
            counts["packages"] += 1
        pkgs[code] = pkg
    reward = db.scalar(select(Package).where(Package.code == "RW-1G-3D"))
    if reward is None:
        reward = Package(
            code="RW-1G-3D",
            name="1 GB Bonus (3 days)",
            kind=PackageKind.data,
            data_mb=1024,
            minutes=0,
            sms=0,
            validity_days=3,
            price=D("0"),
            is_active=False,
        )
        db.add(reward)
        counts["packages"] += 1
    db.flush()

    subs: dict[str, Subscriber] = {}
    for msisdn, name, plan, district, joined, bal, due, points, (lo, hi) in PERSONAS:
        sub = Subscriber(
            msisdn=msisdn,
            full_name=name,
            plan_type=PlanType(plan),
            district=district,
            joined_on=joined,
            reward_points=points,
        )
        db.add(sub)
        db.flush()
        db.add(Balance(subscriber_id=sub.id, main_balance=D(bal), postpaid_due=D(due)))
        subs[msisdn] = sub
        counts["subscribers"] += 1

        for code, data, mins, sms, exp_days in SUBSCRIPTIONS[msisdn]:
            pkg = pkgs[code]
            db.add(
                Subscription(
                    subscriber_id=sub.id,
                    package_id=pkg.id,
                    data_left_mb=data,
                    minutes_left=mins,
                    sms_left=sms,
                    activated_at=now - timedelta(days=pkg.validity_days - exp_days),
                    expires_at=now + timedelta(days=exp_days),
                    auto_renew=False,
                    status=SubscriptionStatus.active,
                )
            )
            counts["subscriptions"] += 1

        # 30 days of usage; only the vas events carry a charge.
        for back in range(30, 0, -1):
            day = today - timedelta(days=back)
            db.add(
                UsageEvent(
                    subscriber_id=sub.id,
                    kind=UsageKind.data,
                    amount=D(rng.randint(lo, hi)),
                    unit="MB",
                    charge=D("0"),
                    description="Mobile data",
                    occurred_at=_local_dt(day, _rand_time(rng), tz),
                )
            )
            counts["usage_events"] += 1
            for _ in range(rng.randint(0, 6)):
                db.add(
                    UsageEvent(
                        subscriber_id=sub.id,
                        kind=UsageKind.voice,
                        amount=D(rng.randint(1, 12)),
                        unit="min",
                        charge=D("0"),
                        description="Voice call",
                        occurred_at=_local_dt(day, _rand_time(rng), tz),
                    )
                )
                counts["usage_events"] += 1
            for _ in range(rng.randint(0, 3)):
                db.add(
                    UsageEvent(
                        subscriber_id=sub.id,
                        kind=UsageKind.sms,
                        amount=D(1),
                        unit="sms",
                        charge=D("0"),
                        description="SMS",
                        occurred_at=_local_dt(day, _rand_time(rng), tz),
                    )
                )
                counts["usage_events"] += 1
        for desc, charge in rng.sample(VAS, rng.choice([2, 3])):
            day = today - timedelta(days=rng.randint(1, 25))
            db.add(
                UsageEvent(
                    subscriber_id=sub.id,
                    kind=UsageKind.vas,
                    amount=D(1),
                    unit="item",
                    charge=charge,
                    description=desc,
                    occurred_at=_local_dt(day, time(6, 0), tz),
                )
            )
            counts["usage_events"] += 1
    db.flush()

    def txn(msisdn, ttype, channel, amount, when, status, *, pkg=None, reason=None):
        db.add(
            Transaction(
                ref=next_ref(db),
                subscriber_id=subs[msisdn].id,
                type=ttype,
                channel=channel,
                amount=D(amount),
                target_msisdn=msisdn if ttype == TxnType.recharge else None,
                package_id=pkg.id if pkg else None,
                status=status,
                failure_reason=reason,
                created_at=when,
            )
        )
        counts["transactions"] += 1

    st, rc, pu = TxnStatus, TxnType.recharge, TxnType.purchase
    sam, rafi = "01712342841", "01812347392"
    txn(sam, rc, TxnChannel.bkash, "200", now - timedelta(hours=2), st.success)
    txn(sam, rc, TxnChannel.nagad, "100", now - timedelta(days=8), st.success)
    txn(sam, rc, TxnChannel.bkash, "300", now - timedelta(days=12), st.failed,
        reason="Payment timed out")
    txn(sam, pu, TxnChannel.balance, "399", now - timedelta(days=1), st.success,
        pkg=pkgs["B15-300"])
    txn(rafi, rc, TxnChannel.nagad, "300", now - timedelta(hours=1), st.pending)

    def case(msisdn, category, desc, status, *, priority=CasePriority.normal, ref=None,
             source=CaseSource.agent, age):
        when = now - age
        db.add(
            SupportCase(
                ref=ref or f"TC-{db.scalar(case_ref_seq.next_value())}",
                subscriber_id=subs[msisdn].id,
                category=category,
                description=desc,
                priority=priority,
                status=status,
                source=source,
                resolved_at=when + timedelta(hours=6) if status == CaseStatus.resolved else None,
                created_at=when,
            )
        )
        counts["cases"] += 1

    case(sam, "Recharge balance not updated",
         "Recharge of ৳300 via bKash did not reflect in my balance.",
         CaseStatus.in_review, ref="TC-2048", age=timedelta(days=2))
    case(sam, "Package activation confirmation",
         "Asked for confirmation that my pack was activated.",
         CaseStatus.resolved, ref="TC-1986", age=timedelta(days=40))
    case("01612341109", "Slow mobile data", "Mobile data has been very slow in the evenings.",
         CaseStatus.open, source=CaseSource.portal, age=timedelta(hours=5))
    case("01512346620", "Unexpected data deduction",
         "Data balance dropped sharply overnight without use.",
         CaseStatus.open, priority=CasePriority.high, age=timedelta(hours=20))
    case("01512346620", "SIM replacement query",
         "How to replace a damaged SIM and keep my number.",
         CaseStatus.resolved, age=timedelta(days=30))

    tomorrow = today + timedelta(days=1)
    db.add(
        NetworkIncident(
            district="Sylhet",
            area="Sylhet Sadar",
            kind=IncidentKind.congestion,
            status=IncidentStatus.investigating,
            message="Some subscribers may experience slower data speeds during peak hours.",
            starts_at=now - timedelta(hours=2),
            ends_at=None,
        )
    )
    db.add(
        NetworkIncident(
            district="Gazipur",
            area="Gazipur Sadar",
            kind=IncidentKind.maintenance,
            status=IncidentStatus.scheduled,
            message="Planned maintenance; short interruptions are possible.",
            starts_at=_local_dt(tomorrow, time(2, 0), tz),
            ends_at=_local_dt(tomorrow, time(3, 30), tz),
        )
    )
    counts["incidents"] = 2

    ends = today + timedelta(days=60)
    db.add(
        Offer(
            title="20 GB + 200 min exclusive",
            description="Our exclusive bundle: 20 GB data and 200 minutes for 30 days.",
            package_id=pkgs["B20-200"].id,
            audience=OfferAudience.all,
            starts_on=today,
            ends_on=ends,
        )
    )
    db.add(
        Offer(
            title="1 GB bonus for 700 points",
            description="Redeem 700 reward points for a 1 GB bonus valid for 3 days.",
            package_id=reward.id,
            points_cost=700,
            audience=OfferAudience.all,
            starts_on=today,
            ends_on=ends,
        )
    )
    db.add(
        Offer(
            title="10% cashback on ৳200+ recharge",
            description="Get 10% cashback (up to ৳30) on any recharge of ৳200 or more.",
            cashback_percent=D("10"),
            cashback_cap=D("30"),
            min_recharge=D("200"),
            audience=OfferAudience.prepaid,
            starts_on=today,
            ends_on=ends,
        )
    )
    counts["offers"] = 3
    db.flush()
    return counts
