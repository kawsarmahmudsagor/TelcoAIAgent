"""Facts worth one extra line after an account answer ("your bonus runs out today").

The tools append them to their output (see block()) so the agent can turn a bare
figure into something useful without hunting for a hook itself: each one is
computed from the account here, so the model never invents one. Ordered by how
much they matter to the customer right now; the prompt says to use at most one.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.telco_format import format_amount, format_data
from app.bss import rewards
from app.bss.clock import local_day_start, local_tz
from app.bss.types import AccountSummary
from app.models.telco import (
    Package,
    PlanType,
    Transaction,
    TxnStatus,
    TxnType,
    UsageEvent,
    UsageKind,
)

# Data left below this, across active packs that still have some, is "almost out".
LOW_DATA_MB = 300
# This week's data counts as unusual when it is this many times the usual week
# and at least ABOVE_NORM_MIN_MB more (a jump from 50 MB to 120 MB isn't news).
ABOVE_NORM_FACTOR = Decimal("1.5")
ABOVE_NORM_MIN_MB = 500
# The usual week: the average of the weeks before this one.
_NORM_WEEKS = 3

_HEADER = (
    "Worth mentioning, if it fits the question (at most one, in your own words, "
    "then offer the matching next step):"
)


def block(highlights: list[str]) -> str:
    """The lines a tool appends to its output; empty when there's nothing."""
    if not highlights:
        return ""
    return "\n" + "\n".join([_HEADER, *(f"- {h}" for h in highlights)])


def relative_day(when: datetime, today: date) -> str | None:
    """'today' or 'tomorrow' for an expiry that close, else None."""
    day = when.astimezone(local_tz()).date()
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return "tomorrow"
    return None


def account_highlights(db: Session, s: AccountSummary, now: datetime) -> list[str]:
    today = now.astimezone(local_tz()).date()
    out: list[str] = []
    for v in s.subscriptions:
        when = relative_day(v.expires_at, today)
        if when and not v.auto_renew:
            out.append(f"Their {v.package_name} expires {when} and doesn't auto-renew.")
    data_left = s.totals.data_left_mb
    if 0 < data_left < LOW_DATA_MB:
        out.append(f"Only {format_data(data_left)} data left across their packages.")
    elif data_left == 0:
        # Out of data only matters to someone who uses it.
        week = _data_between(db, s.subscriber_id, local_day_start(today - timedelta(days=6)), now)
        if week > 0:
            out.append(
                f"They have no data left in any package, though they used {format_data(int(week))} "
                "this week."
            )
    if s.plan_type == PlanType.prepaid:
        usual = _usual_pack(db, s.subscriber_id)
        if usual is not None and s.main_balance < usual.price:
            out.append(
                f"Their balance is below the price of the package they last bought, {usual.name} "
                f"({format_amount(usual.price)}): renewing it needs a recharge first."
            )
    redeemable = _redeemable(db, s.subscriber_id, s.reward_points, now)
    if redeemable:
        cheapest = min(redeemable, key=lambda o: o.points_cost)
        more = f" and {len(redeemable) - 1} more" if len(redeemable) > 1 else ""
        out.append(
            f"Their {s.reward_points} points can be redeemed now, e.g. {cheapest.title} for "
            f"{cheapest.points_cost} points{more} (details from get_offers_and_points)."
        )
    return out


def usage_highlights(db: Session, subscriber_id: UUID, now: datetime) -> list[str]:
    """This week's data against their usual week."""
    today = now.astimezone(local_tz()).date()
    week_start = local_day_start(today - timedelta(days=6))
    norm_start = local_day_start(today - timedelta(days=6 + 7 * _NORM_WEEKS))
    usual = _data_between(db, subscriber_id, norm_start, week_start - timedelta(microseconds=1))
    usual /= _NORM_WEEKS
    this_week = _data_between(db, subscriber_id, week_start, now)
    if usual > 0 and this_week >= usual * ABOVE_NORM_FACTOR and this_week - usual >= ABOVE_NORM_MIN_MB:
        return [
            f"This week's data, {format_data(int(this_week))}, is well above their usual "
            f"{format_data(int(usual))} a week."
        ]
    return []


def _data_between(db: Session, subscriber_id: UUID, start: datetime, end: datetime) -> Decimal:
    """Data MB used from `start` to `end`, both inclusive."""
    total = db.scalar(
        select(func.coalesce(func.sum(UsageEvent.amount), 0)).where(
            UsageEvent.subscriber_id == subscriber_id,
            UsageEvent.kind == UsageKind.data,
            UsageEvent.occurred_at >= start,
            UsageEvent.occurred_at <= end,
        )
    )
    return Decimal(total or 0)


def _usual_pack(db: Session, subscriber_id: UUID) -> Package | None:
    """The pack they bought most recently."""
    return db.scalar(
        select(Package)
        .join(Transaction, Transaction.package_id == Package.id)
        .where(
            Transaction.subscriber_id == subscriber_id,
            Transaction.type == TxnType.purchase,
            Transaction.status == TxnStatus.success,
        )
        .order_by(Transaction.created_at.desc())
        .limit(1)
    )


def points_note(db: Session, subscriber_id: UUID, points: int, now: datetime) -> str:
    """What their points are worth today, for the "Reward points" line: without it
    the model guesses ("enough to redeem an offer") when the answer is no."""
    offers = rewards.get_offers_and_points(db, subscriber_id, now=now).offers
    costs = sorted(o.points_cost for o in offers if o.points_cost is not None)
    if not costs:
        return ""
    can = sum(1 for c in costs if c <= points)
    if can:
        return f" (enough for {can} reward{'s' if can > 1 else ''} now)"
    return f" (not enough for any reward yet: the cheapest needs {costs[0]} points)"


def _redeemable(db: Session, subscriber_id: UUID, points: int, now: datetime) -> list:
    if points <= 0:
        return []
    offers = rewards.get_offers_and_points(db, subscriber_id, now=now).offers
    return [o for o in offers if o.points_cost is not None and o.points_cost <= points]
