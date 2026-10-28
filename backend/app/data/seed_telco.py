"""Demo data for the telco assistant: packages, five personas with balances,
subscriptions, 30 days of usage, transactions and cases, two network incidents
and the offers: pack deals, points redemptions and recharge cashback. Written straight through the ORM (history, not replayed into
balances)."""

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.bss._txn import next_ref
from app.bss.recharge import points_for
from app.config import get_settings
from app.data.personas import FARHANA, NUSRAT, RAFI, SAMIHA, TANVIR
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
    ("D2-3D", "2 GB 3 Days", "data", 2048, 0, 0, 3, 49, None),
    ("D3-3D", "3 GB Weekend", "data", 3072, 0, 0, 3, 69, "WEEKEND"),
    ("D5-7D", "5 GB Weekly", "data", 5120, 0, 0, 7, 109, None),
    ("D8-7D", "8 GB Weekly", "data", 8192, 0, 0, 7, 149, "BEST VALUE"),
    ("D10-15D", "10 GB 15 Days", "data", 10240, 0, 0, 15, 229, None),
    ("D15-30D", "15 GB Monthly", "data", 15360, 0, 0, 30, 349, None),
    ("D30-30D", "30 GB Monthly", "data", 30720, 0, 0, 30, 549, None),
    ("D50-30D", "50 GB Monthly", "data", 51200, 0, 0, 30, 749, None),
    ("D100-30D", "100 GB Monthly", "data", 102400, 0, 0, 30, 999, "HEAVY USER"),
    ("V50-3D", "50 Minutes", "voice", 0, 50, 0, 3, 39, None),
    ("V100-7D", "100 Minutes", "voice", 0, 100, 0, 7, 79, "SHORT CALLS"),
    ("V300-30D", "300 Minutes", "voice", 0, 300, 0, 30, 199, "VOICE"),
    ("V600-30D", "600 Minutes", "voice", 0, 600, 0, 30, 349, None),
    ("V1000-30D", "1000 Minutes", "voice", 0, 1000, 0, 30, 499, None),
    ("B2-50", "2 GB + 50 min", "bundle", 2048, 50, 0, 3, 79, "STARTER"),
    ("B5-100", "5 GB + 100 min", "bundle", 5120, 100, 0, 7, 179, None),
    ("B10-150", "10 GB + 150 min", "bundle", 10240, 150, 0, 15, 299, None),
    ("B15-300", "Smart 15 GB + 300 min", "bundle", 15360, 300, 0, 30, 399, "POPULAR"),
    ("B20-200", "20 GB + 200 min", "bundle", 20480, 200, 0, 30, 449, "EXCLUSIVE"),
    ("B40-500", "40 GB + 500 min", "bundle", 40960, 500, 0, 30, 799, None),
    ("B60-1000", "60 GB + 1000 min + 100 SMS", "bundle", 61440, 1000, 100, 30, 999, "PREMIUM"),
    ("S100-30D", "100 SMS", "sms", 0, 0, 100, 30, 29, None),
    ("S500-30D", "500 SMS", "sms", 0, 0, 500, 30, 79, None),
    ("S1000-30D", "1000 SMS", "sms", 0, 0, 1000, 30, 129, None),
]

# Packs only reward points buy: inactive (not on sale) and free.
# code, name, kind, data_mb, minutes, sms, days
REWARD_PACKAGES = [
    ("RW-500M-1D", "500 MB Bonus (1 day)", "data", 512, 0, 0, 1),
    ("RW-1G-3D", "1 GB Bonus (3 days)", "data", 1024, 0, 0, 3),
    ("RW-30MIN-7D", "30 Minutes Bonus (7 days)", "voice", 0, 30, 0, 7),
    ("RW-3G-7D", "3 GB Bonus (7 days)", "data", 3072, 0, 0, 7),
    ("RW-B5-7D", "5 GB + 100 min Bonus (7 days)", "bundle", 5120, 100, 0, 7),
    ("RW-10G-30D", "10 GB Bonus (30 days)", "data", 10240, 0, 0, 30),
]

# msisdn, name, plan, district, joined_on, balance, due, points, daily data MB range
PERSONAS = [
    (SAMIHA, "Samiha Khan", "prepaid", "Dhaka", date(2024, 3, 14), "486.50", "0", 840, (150, 350)),
    (RAFI, "Rafi Ahmed", "prepaid", "Chattogram", date(2023, 9, 2), "42.00", "0", 120, (300, 600)),
    (NUSRAT, "Nusrat Mahmud", "postpaid", "Rajshahi", date(2022, 6, 21), "0", "1240.00", 300, (600, 1200)),
    (TANVIR, "Tanvir Hasan", "prepaid", "Sylhet", date(2024, 11, 5), "215.00", "0", 60, (200, 500)),
    (FARHANA, "Farhana Islam", "prepaid", "Gazipur", date(2021, 12, 9), "730.25", "0", 2150, (250, 450)),
]

# msisdn -> [(package code, data_left, minutes_left, sms_left, expires in days)]
SUBSCRIPTIONS = {
    SAMIHA: [("B15-300", 8602, 182, 0, 3), ("S100-30D", 0, 0, 74, 20)],
    RAFI: [("D8-7D", 2100, 0, 0, 5)],
    NUSRAT: [("B40-500", 30000, 410, 0, 18)],
    TANVIR: [("D15-30D", 1200, 0, 0, 11)],
    FARHANA: [("B20-200", 12000, 150, 0, 20)],
}

PACKAGE_CODES = [p[0] for p in PACKAGES] + [p[0] for p in REWARD_PACKAGES]

# Every offer runs 60 days from the seed day. Keys left out are None; "package"
# is a code from PACKAGES or REWARD_PACKAGES.
OFFERS = [
    # Pack deals.
    {
        "title": "20 GB + 200 min exclusive",
        "description": "Our exclusive bundle: 20 GB data and 200 minutes for 30 days.",
        "package": "B20-200",
        "audience": "all",
    },
    {
        "title": "2 GB + 50 min starter",
        "description": "Try us light: 2 GB data and 50 minutes for 3 days at ৳79.",
        "package": "B2-50",
        "audience": "prepaid",
    },
    {
        "title": "60 GB + 1000 min premium",
        "description": "Our biggest bundle: 60 GB, 1000 minutes and 100 SMS for 30 days.",
        "package": "B60-1000",
        "audience": "postpaid",
    },
    # Points redemptions, cheapest first.
    {
        "title": "500 MB bonus for 300 points",
        "description": "Redeem 300 reward points for a 500 MB bonus valid for 1 day.",
        "package": "RW-500M-1D",
        "points_cost": 300,
        "audience": "all",
    },
    {
        "title": "30 bonus minutes for 400 points",
        "description": "Redeem 400 reward points for 30 bonus minutes valid for 7 days.",
        "package": "RW-30MIN-7D",
        "points_cost": 400,
        "audience": "all",
    },
    {
        "title": "1 GB bonus for 700 points",
        "description": "Redeem 700 reward points for a 1 GB bonus valid for 3 days.",
        "package": "RW-1G-3D",
        "points_cost": 700,
        "audience": "all",
    },
    {
        "title": "3 GB bonus for 1,500 points",
        "description": "Redeem 1,500 reward points for a 3 GB bonus valid for 7 days.",
        "package": "RW-3G-7D",
        "points_cost": 1500,
        "audience": "all",
    },
    {
        "title": "5 GB + 100 min for 2,500 points",
        "description": "Redeem 2,500 reward points for 5 GB and 100 minutes valid for 7 days.",
        "package": "RW-B5-7D",
        "points_cost": 2500,
        "audience": "all",
    },
    {
        "title": "10 GB bonus for 4,000 points",
        "description": "Redeem 4,000 reward points for a 10 GB bonus valid for 30 days.",
        "package": "RW-10G-30D",
        "points_cost": 4000,
        "audience": "all",
    },
    # Recharge cashback; a recharge gets the single best one it qualifies for.
    {
        "title": "5% cashback on ৳100+ recharge",
        "description": "Get 5% cashback (up to ৳10) on any recharge of ৳100 or more.",
        "cashback_percent": "5",
        "cashback_cap": "10",
        "min_recharge": "100",
        "audience": "prepaid",
    },
    {
        "title": "10% cashback on ৳200+ recharge",
        "description": "Get 10% cashback (up to ৳30) on any recharge of ৳200 or more.",
        "cashback_percent": "10",
        "cashback_cap": "30",
        "min_recharge": "200",
        "audience": "prepaid",
    },
    {
        "title": "15% cashback on ৳500+ recharge",
        "description": "Get 15% cashback (up to ৳75) on any recharge of ৳500 or more.",
        "cashback_percent": "15",
        "cashback_cap": "75",
        "min_recharge": "500",
        "audience": "prepaid",
    },
]

# (district, area) of the seeded incidents and the seeded offers' titles, so
# reset() can find them again.
INCIDENT_AREAS = [("Sylhet", "Sylhet Sadar"), ("Gazipur", "Gazipur Sadar")]
OFFER_TITLES = [o["title"] for o in OFFERS]

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
    for code, name, kind, mb, mins, sms, days in REWARD_PACKAGES:
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
                price=D("0"),
                is_active=False,
            )
            db.add(pkg)
            counts["packages"] += 1
        pkgs[code] = pkg
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
                points_earned=(
                    points_for(D(amount))
                    if ttype == TxnType.recharge and status == TxnStatus.success
                    else 0
                ),
                status=status,
                failure_reason=reason,
                created_at=when,
            )
        )
        counts["transactions"] += 1

    st, rc, pu = TxnStatus, TxnType.recharge, TxnType.purchase
    sam, rafi = SAMIHA, RAFI
    txn(sam, rc, TxnChannel.bkash, "200", now - timedelta(hours=2), st.success)
    txn(sam, rc, TxnChannel.nagad, "100", now - timedelta(days=8), st.success)
    txn(sam, rc, TxnChannel.bkash, "300", now - timedelta(days=12), st.failed,
        reason="Payment timed out")
    # Dated when the pack was activated (validity minus days left).
    b15 = pkgs["B15-300"]
    b15_left = next(d[4] for d in SUBSCRIPTIONS[sam] if d[0] == b15.code)
    txn(sam, pu, TxnChannel.balance, "399",
        now - timedelta(days=b15.validity_days - b15_left), st.success, pkg=b15)
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
    case(TANVIR, "Slow mobile data", "Mobile data has been very slow in the evenings.",
         CaseStatus.open, source=CaseSource.portal, age=timedelta(hours=5))
    case(FARHANA, "Unexpected data deduction",
         "Data balance dropped sharply overnight without use.",
         CaseStatus.open, priority=CasePriority.high, age=timedelta(hours=20))
    case(FARHANA, "SIM replacement query",
         "How to replace a damaged SIM and keep my number.",
         CaseStatus.resolved, age=timedelta(days=30))

    tomorrow = today + timedelta(days=1)
    db.add(
        NetworkIncident(
            district=INCIDENT_AREAS[0][0],
            area=INCIDENT_AREAS[0][1],
            kind=IncidentKind.congestion,
            status=IncidentStatus.investigating,
            message="Some subscribers may experience slower data speeds during peak hours.",
            starts_at=now - timedelta(hours=2),
            ends_at=None,
        )
    )
    db.add(
        NetworkIncident(
            district=INCIDENT_AREAS[1][0],
            area=INCIDENT_AREAS[1][1],
            kind=IncidentKind.maintenance,
            status=IncidentStatus.scheduled,
            message="Planned maintenance; short interruptions are possible.",
            starts_at=_local_dt(tomorrow, time(2, 0), tz),
            ends_at=_local_dt(tomorrow, time(3, 30), tz),
        )
    )
    counts["incidents"] = 2

    ends = today + timedelta(days=60)
    for o in OFFERS:
        cashback = o.get("cashback_percent")
        db.add(
            Offer(
                title=o["title"],
                description=o["description"],
                package_id=pkgs[o["package"]].id if "package" in o else None,
                points_cost=o.get("points_cost"),
                cashback_percent=D(cashback) if cashback else None,
                cashback_cap=D(o["cashback_cap"]) if cashback else None,
                min_recharge=D(o["min_recharge"]) if cashback else None,
                audience=OfferAudience(o["audience"]),
                starts_on=today,
                ends_on=ends,
            )
        )
    counts["offers"] = len(OFFERS)
    db.flush()
    return counts


def clear(db: Session) -> dict[str, int]:
    """Delete the demo rows: every subscriber outside the reserved 01999 test
    range (balances, subscriptions, usage, transactions, cases, OTPs,
    notifications and audit rows cascade; conversations keep their row with
    subscriber_id set to NULL), the seeded incidents and offers, and the seeded
    packages nothing else references. Caller commits."""
    out = {}
    out["subscribers"] = db.execute(
        delete(Subscriber).where(~Subscriber.msisdn.like("01999%"))
    ).rowcount
    out["incidents"] = sum(
        db.execute(
            delete(NetworkIncident).where(
                NetworkIncident.district == district, NetworkIncident.area == area
            )
        ).rowcount
        for district, area in INCIDENT_AREAS
    )
    out["offers"] = db.execute(
        delete(Offer).where(
            Offer.title.in_(OFFER_TITLES),
            ~exists().where(Transaction.offer_id == Offer.id),
        )
    ).rowcount
    out["packages"] = db.execute(
        delete(Package).where(
            Package.code.in_(PACKAGE_CODES),
            ~exists().where(Subscription.package_id == Package.id),
            ~exists().where(Transaction.package_id == Package.id),
            ~exists().where(Offer.package_id == Package.id),
        )
    ).rowcount
    db.expire_all()
    return out


def reset(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """clear() then seed() relative to `now`. Caller commits."""
    clear(db)
    return seed(db, now=now)
