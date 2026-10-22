from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.bss import network
from app.bss.clock import local_day_start, local_tz, utc_now
from app.bss.errors import InvalidRequest, SubscriberNotFound
from app.bss.types import (
    AccountSummary,
    Allowance,
    Deduction,
    SubscriptionView,
    UsageBreakdown,
    UsageTotals,
)
from app.models.telco import (
    Balance,
    CaseStatus,
    Package,
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
)


def _mask(msisdn: str) -> str:
    return f"{msisdn[:3]}••••{msisdn[-4:]}"


def get_account_summary(
    db: Session, subscriber_id: UUID, *, now: datetime | None = None
) -> AccountSummary:
    now = now or utc_now()
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise SubscriberNotFound()
    bal = db.get(Balance, subscriber_id)

    rows = db.execute(
        select(Subscription, Package)
        .join(Package, Package.id == Subscription.package_id)
        .where(
            Subscription.subscriber_id == subscriber_id,
            Subscription.status == SubscriptionStatus.active,
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at)
    ).all()
    views = [
        SubscriptionView(
            package_code=pkg.code,
            package_name=pkg.name,
            data_left_mb=s.data_left_mb,
            minutes_left=s.minutes_left,
            sms_left=s.sms_left,
            expires_at=s.expires_at,
            auto_renew=s.auto_renew,
        )
        for s, pkg in rows
    ]
    totals = Allowance(
        data_left_mb=sum(v.data_left_mb for v in views),
        minutes_left=sum(v.minutes_left for v in views),
        sms_left=sum(v.sms_left for v in views),
    )
    open_cases = db.scalar(
        select(func.count())
        .select_from(SupportCase)
        .where(
            SupportCase.subscriber_id == subscriber_id,
            SupportCase.status != CaseStatus.resolved,
        )
    )
    incidents = db.scalar(
        select(func.count()).select_from(
            network.active_incidents_query(sub.district, now).subquery()
        )
    )
    return AccountSummary(
        subscriber_id=sub.id,
        full_name=sub.full_name,
        masked_msisdn=_mask(sub.msisdn),
        plan_type=sub.plan_type,
        district=sub.district,
        main_balance=bal.main_balance if bal else Decimal("0"),
        postpaid_due=bal.postpaid_due if bal else Decimal("0"),
        reward_points=sub.reward_points,
        totals=totals,
        subscriptions=views,
        nearest_expiry=views[0].expires_at if views else None,
        open_cases=open_cases or 0,
        district_incidents=incidents or 0,
    )


def get_usage_breakdown(
    db: Session,
    subscriber_id: UUID,
    *,
    period_days: int = 30,
    kind: UsageKind | None = None,
    now: datetime | None = None,
) -> UsageBreakdown:
    if period_days not in (7, 30):
        raise InvalidRequest("period_days must be 7 or 30")
    now = now or utc_now()
    if db.get(Subscriber, subscriber_id) is None:
        raise SubscriberNotFound()

    today = now.astimezone(local_tz()).date()
    first_day = today - timedelta(days=period_days - 1)
    conds = [
        UsageEvent.subscriber_id == subscriber_id,
        UsageEvent.occurred_at >= local_day_start(first_day),
        UsageEvent.occurred_at <= now,
    ]
    if kind is not None:
        conds.append(UsageEvent.kind == kind)

    agg: dict[UsageKind, UsageTotals] = {}
    per_day: dict[date, Decimal] = {}
    for e in db.scalars(select(UsageEvent).where(*conds)):
        t = agg.get(e.kind)
        if t is None:
            agg[e.kind] = UsageTotals(kind=e.kind, amount=e.amount, unit=e.unit, charge=e.charge)
        else:
            t.amount += e.amount
            t.charge += e.charge
        if e.kind == UsageKind.data:
            d = e.occurred_at.astimezone(local_tz()).date()
            per_day[d] = per_day.get(d, Decimal("0")) + e.amount

    daily = [
        (d, per_day.get(d, Decimal("0")))
        for d in (first_day + timedelta(days=i) for i in range(period_days))
    ]
    return UsageBreakdown(
        period_days=period_days,
        totals=sorted(agg.values(), key=lambda t: t.kind.value),
        daily=daily,
    )


def explain_deductions(
    db: Session,
    subscriber_id: UUID,
    *,
    since: datetime | None = None,
    now: datetime | None = None,
) -> list[Deduction]:
    now = now or utc_now()
    since = since or now - timedelta(days=7)
    if db.get(Subscriber, subscriber_id) is None:
        raise SubscriberNotFound()

    out: list[Deduction] = []
    for e in db.scalars(
        select(UsageEvent)
        .where(
            UsageEvent.subscriber_id == subscriber_id,
            UsageEvent.charge > 0,
            UsageEvent.occurred_at >= since,
            UsageEvent.occurred_at <= now,
        )
        .order_by(UsageEvent.occurred_at.desc())
        .limit(20)
    ):
        out.append(
            Deduction(
                occurred_at=e.occurred_at,
                description=e.description,
                amount=e.charge,
                source="usage",
            )
        )
    for t, pkg in db.execute(
        select(Transaction, Package)
        .outerjoin(Package, Package.id == Transaction.package_id)
        .where(
            Transaction.subscriber_id == subscriber_id,
            Transaction.type == TxnType.purchase,
            Transaction.channel == TxnChannel.balance,
            Transaction.status == TxnStatus.success,
            Transaction.created_at >= since,
            Transaction.created_at <= now,
        )
        .order_by(Transaction.created_at.desc())
        .limit(20)
    ):
        out.append(
            Deduction(
                occurred_at=t.created_at,
                description=f"Pack purchase: {pkg.name}" if pkg else "Pack purchase",
                amount=t.amount,
                source="purchase",
            )
        )
    out.sort(key=lambda d: d.occurred_at, reverse=True)
    return out[:20]
