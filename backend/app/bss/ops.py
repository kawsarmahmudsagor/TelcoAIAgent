"""Admin reads: control-center overview, subscriber and transaction lists."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.bss import accounts, monitor, network, notifications
from app.bss.clock import local_day_bounds, local_day_start, local_tz, utc_now
from app.bss.errors import SubscriberNotFound
from app.bss.types import CaseView, TransactionView
from app.models.telco import (
    Balance,
    CasePriority,
    CaseSource,
    CaseStatus,
    IncidentKind,
    IncidentStatus,
    NetworkIncident,
    Package,
    PlanType,
    Subscriber,
    SubscriberStatus,
    SupportCase,
    Transaction,
    TxnStatus,
    TxnType,
)

_HIGH_CASE_AGE = timedelta(hours=2)
_FALLBACK_ALERT = 0.08
_FALLBACK_MIN_TURNS = 10


def _digits(q: str) -> str:
    return "".join(ch for ch in q if ch.isdigit())


def _rate(success: int, failed: int) -> float | None:
    return success / (success + failed) if success + failed else None


def _status_stats(
    db: Session, start: datetime, end: datetime | None = None
) -> dict[TxnStatus, tuple[int, Decimal]]:
    """(count, amount sum) per status for transactions created in [start, end)."""
    q = select(
        Transaction.status, func.count(), func.coalesce(func.sum(Transaction.amount), 0)
    ).where(Transaction.created_at >= start)
    if end is not None:
        q = q.where(Transaction.created_at < end)
    return {s: (n, Decimal(a)) for s, n, a in db.execute(q.group_by(Transaction.status))}


def _count(stats: dict[TxnStatus, tuple[int, Decimal]], status: TxnStatus) -> int:
    return stats.get(status, (0, Decimal(0)))[0]


def transaction_stats(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    start, end = local_day_bounds(now or utc_now())
    stats = _status_stats(db, start, end)
    success, pending, failed = (
        _count(stats, s) for s in (TxnStatus.success, TxnStatus.pending, TxnStatus.failed)
    )
    return {
        "volume": stats.get(TxnStatus.success, (0, Decimal(0)))[1],
        "attempts": success + pending + failed,
        "success": success,
        "pending": pending,
        "failed": failed,
        "success_rate": _rate(success, failed),
    }


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def overview(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    day_start, day_end = local_day_bounds(now)
    day_ago = now - timedelta(hours=24)

    plan_counts = dict(
        db.execute(select(Subscriber.plan_type, func.count()).group_by(Subscriber.plan_type)).all()
    )
    prepaid = plan_counts.get(PlanType.prepaid, 0)
    postpaid = plan_counts.get(PlanType.postpaid, 0)

    recharge_count, recharge_amount = db.execute(
        select(func.count(), func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.type == TxnType.recharge,
            Transaction.status == TxnStatus.success,
            Transaction.created_at >= day_start,
            Transaction.created_at < day_end,
        )
    ).one()

    open_cases = SupportCase.status != CaseStatus.resolved
    high = SupportCase.priority == CasePriority.high
    n_open = db.scalar(select(func.count()).select_from(SupportCase).where(open_cases))
    n_high = db.scalar(select(func.count()).select_from(SupportCase).where(open_cases, high))
    n_stale_high = db.scalar(
        select(func.count())
        .select_from(SupportCase)
        .where(open_cases, high, SupportCase.created_at < now - _HIGH_CASE_AGE)
    )

    # 7 local days, oldest first, zero-filled.
    today = now.astimezone(local_tz()).date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    first = local_day_start(days[0])
    tz_name = str(local_tz())
    txn_day = func.date(func.timezone(tz_name, Transaction.created_at))
    recharge_by_day = dict(
        db.execute(
            select(txn_day, func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.type == TxnType.recharge,
                Transaction.status == TxnStatus.success,
                Transaction.created_at >= first,
            )
            .group_by(txn_day)
        ).all()
    )
    case_day = func.date(func.timezone(tz_name, SupportCase.created_at))
    cases_by_day = dict(
        db.execute(
            select(case_day, func.count()).where(SupportCase.created_at >= first).group_by(case_day)
        ).all()
    )
    activity = [
        {
            "date": d,
            "recharge_amount": Decimal(recharge_by_day.get(d, 0)),
            "cases_created": cases_by_day.get(d, 0),
        }
        for d in days
    ]

    last_24h = _status_stats(db, day_ago)
    pending_now = (
        db.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.status == TxnStatus.pending)
        )
        or 0
    )
    incidents = db.scalars(
        select(NetworkIncident)
        .where(
            NetworkIncident.status != IncidentStatus.resolved,
            NetworkIncident.starts_at <= now,
            (NetworkIncident.ends_at.is_(None)) | (NetworkIncident.ends_at > now),
        )
        .order_by(NetworkIncident.starts_at)
    ).all()

    m = monitor.metrics(db, since=day_ago)

    attention: list[dict[str, Any]] = []
    if pending_now:
        attention.append(
            {
                "kind": "pending_transactions",
                "title": f"{_plural(pending_now, 'pending transaction')}",
                "detail": "Waiting for the payment gateway to confirm.",
                "severity": "investigate",
                "href": "/dashboard/transactions?status=pending",
            }
        )
    if n_stale_high:
        attention.append(
            {
                "kind": "high_priority_cases",
                "title": f"{_plural(n_stale_high, 'high-priority case')} open over 2 hours",
                "detail": "Customers are still waiting on these.",
                "severity": "high",
                "href": "/dashboard/cases?priority=high",
            }
        )
    if m["turns"] >= _FALLBACK_MIN_TURNS and m["fallback_rate"] > _FALLBACK_ALERT:
        attention.append(
            {
                "kind": "ai_fallback",
                "title": f"AI fallback rate {m['fallback_rate'] * 100:.0f}% in the last 24 hours",
                "detail": f"{m['turns']} customer turns; review the flagged conversations.",
                "severity": "review",
                "href": "/dashboard/ai-monitor",
            }
        )
    for inc in incidents:
        if inc.kind in (IncidentKind.outage, IncidentKind.congestion):
            attention.append(
                {
                    "kind": f"network_{inc.kind.value}",
                    "title": f"{inc.kind.value.capitalize()} in {inc.area}, {inc.district}",
                    "detail": inc.message,
                    "severity": "high" if inc.kind == IncidentKind.outage else "investigate",
                    "href": "/dashboard/network",
                }
            )

    return {
        "subscribers": {"total": prepaid + postpaid, "prepaid": prepaid, "postpaid": postpaid},
        "recharge_today": {"amount": Decimal(recharge_amount), "count": recharge_count},
        "cases": {"open": n_open or 0, "high_open": n_high or 0},
        "ai": {"chats_24h": m["chats"], "resolution_rate": m["resolution_rate"]},
        "activity": activity,
        "health": {
            "recharge_success_rate_24h": _rate(
                _count(last_24h, TxnStatus.success), _count(last_24h, TxnStatus.failed)
            ),
            "median_first_response_s": m["median_first_response_s"],
            "active_incidents": len(incidents),
            "pending_transactions": pending_now,
        },
        "attention": attention,
    }


def _subscriber_item(sub: Subscriber, bal: Balance | None) -> dict[str, Any]:
    return {
        "id": sub.id,
        "full_name": sub.full_name,
        "msisdn_masked": accounts.mask_msisdn(sub.msisdn),
        "plan_type": sub.plan_type,
        "district": sub.district,
        "status": sub.status,
        "main_balance": bal.main_balance if bal else Decimal("0"),
        "postpaid_due": bal.postpaid_due if bal else Decimal("0"),
        "joined_on": sub.joined_on,
    }


def list_subscribers(
    db: Session,
    *,
    q: str | None = None,
    plan_type: PlanType | None = None,
    status: SubscriberStatus | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    base: Select = select(Subscriber, Balance).outerjoin(
        Balance, Balance.subscriber_id == Subscriber.id
    )
    if q and q.strip():
        conds = [Subscriber.full_name.ilike(f"%{q.strip()}%")]
        digits = _digits(q)
        if digits:
            conds.append(Subscriber.msisdn.contains(digits))
        base = base.where(or_(*conds))
    if plan_type is not None:
        base = base.where(Subscriber.plan_type == plan_type)
    if status is not None:
        base = base.where(Subscriber.status == status)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(Subscriber.full_name, Subscriber.id).limit(limit).offset(offset)
    ).all()
    return [_subscriber_item(s, b) for s, b in rows], total


def _txn_view(t: Transaction, package_name: str | None) -> TransactionView:
    return TransactionView(
        ref=t.ref,
        type=t.type,
        channel=t.channel,
        amount=t.amount,
        target_msisdn=accounts.mask_msisdn(t.target_msisdn) if t.target_msisdn else None,
        status=t.status,
        failure_reason=t.failure_reason,
        created_at=t.created_at,
        package_name=package_name,
    )


def subscriber_detail(db: Session, subscriber_id: uuid.UUID) -> dict[str, Any]:
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise SubscriberNotFound()
    txns = db.execute(
        select(Transaction, Package.name)
        .outerjoin(Package, Package.id == Transaction.package_id)
        .where(Transaction.subscriber_id == subscriber_id)
        .order_by(Transaction.created_at.desc())
        .limit(10)
    ).all()
    cases = db.scalars(
        select(SupportCase)
        .where(SupportCase.subscriber_id == subscriber_id)
        .order_by(SupportCase.created_at.desc())
        .limit(10)
    ).all()
    return {
        "subscriber": {
            **_subscriber_item(sub, db.get(Balance, subscriber_id)),
            "reward_points": sub.reward_points,
            "preferred_language": sub.preferred_language,
        },
        "summary": accounts.get_account_summary(db, subscriber_id),
        "transactions": [_txn_view(t, name) for t, name in txns],
        "cases": [CaseView.model_validate(c) for c in cases],
        "notifications": notifications.list_for(db, subscriber_id, limit=10)[1],
    }


def list_transactions(
    db: Session,
    *,
    status: TxnStatus | None = None,
    type: TxnType | None = None,
    q: str | None = None,
    days: int = 7,
    limit: int = 25,
    offset: int = 0,
    now: datetime | None = None,
) -> tuple[list[dict[str, Any]], int]:
    now = now or utc_now()
    base: Select = (
        select(Transaction, Package.name, Subscriber.full_name, Subscriber.msisdn)
        .join(Subscriber, Subscriber.id == Transaction.subscriber_id)
        .outerjoin(Package, Package.id == Transaction.package_id)
        .where(Transaction.created_at >= now - timedelta(days=days))
    )
    if status is not None:
        base = base.where(Transaction.status == status)
    if type is not None:
        base = base.where(Transaction.type == type)
    if q and q.strip():
        conds = [func.lower(Transaction.ref).contains(q.strip().lower())]
        digits = _digits(q)
        if digits:
            conds.append(Subscriber.msisdn.contains(digits))
        base = base.where(or_(*conds))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(Transaction.created_at.desc(), Transaction.id).limit(limit).offset(offset)
    ).all()
    return (
        [
            {
                **_txn_view(t, pkg).model_dump(),
                "subscriber_name": name,
                "msisdn_masked": accounts.mask_msisdn(msisdn),
            }
            for t, pkg, name, msisdn in rows
        ],
        total,
    )


def list_cases(
    db: Session,
    *,
    status: CaseStatus | None = None,
    priority: CasePriority | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """High priority first, then open before resolved, oldest first."""
    base: Select = select(SupportCase, Subscriber.full_name, Subscriber.msisdn).join(
        Subscriber, Subscriber.id == SupportCase.subscriber_id
    )
    if status is not None:
        base = base.where(SupportCase.status == status)
    if priority is not None:
        base = base.where(SupportCase.priority == priority)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.execute(
        base.order_by(
            case((SupportCase.priority == CasePriority.high, 0), else_=1),
            case((SupportCase.status == CaseStatus.resolved, 1), else_=0),
            SupportCase.created_at,
            SupportCase.id,
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return (
        [
            {
                **CaseView.model_validate(c).model_dump(),
                "subscriber_name": name,
                "msisdn_masked": accounts.mask_msisdn(msisdn),
            }
            for c, name, msisdn in rows
        ],
        total,
    )


def case_stats(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    since = now - timedelta(days=7)
    open_cases = SupportCase.status != CaseStatus.resolved
    n_open = db.scalar(select(func.count()).select_from(SupportCase).where(open_cases)) or 0
    n_high = (
        db.scalar(
            select(func.count())
            .select_from(SupportCase)
            .where(open_cases, SupportCase.priority == CasePriority.high)
        )
        or 0
    )
    avg_s = db.scalar(
        select(
            func.avg(func.extract("epoch", SupportCase.resolved_at - SupportCase.created_at))
        ).where(SupportCase.status == CaseStatus.resolved, SupportCase.resolved_at >= since)
    )
    created, by_agent = db.execute(
        select(
            func.count(),
            func.count().filter(SupportCase.source == CaseSource.agent),
        ).where(SupportCase.created_at >= since)
    ).one()
    return {
        "open": n_open,
        "high_open": n_high,
        "avg_resolution_hours_7d": round(float(avg_s) / 3600, 1) if avg_s is not None else None,
        "ai_assisted_share_7d": round(by_agent / created, 3) if created else 0.0,
    }


def network_overview(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or utc_now()
    cutoff = now - timedelta(days=7)
    live = (NetworkIncident.status != IncidentStatus.resolved) & (
        NetworkIncident.ends_at.is_(None) | (NetworkIncident.ends_at > now)
    )
    current = db.scalars(
        select(NetworkIncident)
        .where(live)
        .order_by(NetworkIncident.starts_at, NetworkIncident.area)
    ).all()
    past = db.scalars(
        select(NetworkIncident)
        .where(~live, func.coalesce(NetworkIncident.ends_at, NetworkIncident.updated_at) >= cutoff)
        .order_by(NetworkIncident.ends_at.desc().nulls_last(), NetworkIncident.area)
    ).all()

    health: dict[str, str] = {}
    counts: dict[str, int] = {}
    for inc in current:
        counts[inc.district] = counts.get(inc.district, 0) + 1
        if network.is_active(inc, now) and inc.kind != IncidentKind.maintenance:
            health[inc.district] = "degraded"
        elif inc.kind == IncidentKind.maintenance and health.get(inc.district) != "degraded":
            health[inc.district] = "maintenance"
    names = {d for (d,) in db.execute(select(Subscriber.district).distinct()).all()}
    names |= {i.district for i in (*current, *past)}
    return {
        "districts": [
            {"district": d, "health": health.get(d, "normal"), "incidents": counts.get(d, 0)}
            for d in sorted(names)
        ],
        "incidents": [network.admin_view(i, now) for i in (*current, *past)],
    }
