"""Account read tools: summary, usage breakdown, deduction explanation."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from livekit.agents import RunContext, function_tool

from app.agent import highlights
from app.agent.telco_format import format_amount, format_data, format_day
from app.agent.tools._common import LISTED, listed, parse_enum, run_read
from app.agent.userdata import SessionUserdata
from app.bss import accounts
from app.bss.clock import local_tz, utc_now
from app.bss.errors import InvalidRequest
from app.models.telco import PlanType, UsageKind

def _day_name(d: date) -> str:
    return f"{d:%A} {d.day} {d:%B}"


async def run_get_account_summary(userdata: SessionUserdata) -> str:
    def build(db, sid):
        now = utc_now()
        today = now.astimezone(local_tz()).date()
        s = accounts.get_account_summary(db, sid, now=now)
        lines = [
            f"Customer: {s.full_name}, number {s.masked_msisdn}, {s.plan_type.value}, "
            f"district {s.district}."
        ]
        if s.plan_type == PlanType.prepaid:
            lines.append(f"Main balance: {format_amount(s.main_balance)}.")
        else:
            lines.append(f"Bill due: {format_amount(s.postpaid_due)}.")
        note = highlights.points_note(db, sid, s.reward_points, now)
        lines.append(f"Reward points: {s.reward_points}{note}.")
        if s.subscriptions:
            t = s.totals
            lines.append(
                f"Active packs: {len(s.subscriptions)}. Total left: {format_data(t.data_left_mb)} "
                f"data, {t.minutes_left} minutes, {t.sms_left} SMS."
            )
            packs = []
            for v in s.subscriptions[:LISTED]:
                renew = ", auto-renew on" if v.auto_renew else ""
                expires = format_day(v.expires_at)
                if when := highlights.relative_day(v.expires_at, today):
                    expires = f"{when} ({expires})"
                packs.append(
                    f"- {v.package_name}: {format_data(v.data_left_mb)}, {v.minutes_left} minutes, "
                    f"{v.sms_left} SMS left, expires {expires}{renew}."
                )
            lines += listed(packs, len(s.subscriptions))
        else:
            lines.append("No active packs.")
        lines.append(f"Open support cases: {s.open_cases}.")
        if s.district_incidents:
            lines.append(
                f"Network incidents in their district: {s.district_incidents} "
                "(use check_network_status for details)."
            )
        return "\n".join(lines) + highlights.block(highlights.account_highlights(db, s, now))

    return await run_read(userdata, build)


async def run_get_usage_breakdown(
    userdata: SessionUserdata, period_days: int = 30, kind: str | None = None
) -> str:
    def build(db, sid):
        usage_kind = parse_enum(UsageKind, kind)
        b = accounts.get_usage_breakdown(db, sid, period_days=period_days, kind=usage_kind)
        when = "today" if b.period_days == 1 else f"in the last {b.period_days} days"
        if not b.totals:
            return f"No usage {when}."
        lines = [f"Usage {when}:"]
        for t in b.totals:
            amount = format_data(int(t.amount)) if t.kind == UsageKind.data else f"{int(t.amount)} {t.unit}"
            # A zero charge goes unsaid: "charged 0.00 taka" made the model tell
            # the customer "এগুলোর জন্য কোনো চার্জ হয়নি", which nobody asked.
            charge = f", charged {format_amount(t.charge)}" if t.charge else ""
            lines.append(f"- {t.kind.value}: {amount}{charge}.")
        peak = max(b.daily, key=lambda d: d[1], default=None)
        if peak and peak[1] > 0 and b.period_days > 1:
            lines.append(f"Heaviest data day: {_day_name(peak[0])}, {format_data(int(peak[1]))}.")
        extra = []
        if usage_kind in (None, UsageKind.data):
            extra = highlights.usage_highlights(db, sid, utc_now())
        return "\n".join(lines) + highlights.block(extra)

    return await run_read(userdata, build)


async def run_explain_deductions(userdata: SessionUserdata, days: int = 7) -> str:
    def build(db, sid):
        if not 1 <= days <= 90:
            raise InvalidRequest("days must be between 1 and 90")
        items = accounts.explain_deductions(db, sid, since=utc_now() - timedelta(days=days))
        if not items:
            return f"No balance deductions in the last {days} days."
        total = sum((i.amount for i in items), Decimal("0"))
        lines = [f"{len(items)} deductions in the last {days} days, {format_amount(total)} in total:"]
        lines += listed(
            [
                f"- {format_day(i.occurred_at, with_time=True)}: {i.description}, "
                f"{format_amount(i.amount)} ({i.source})."
                for i in items[:LISTED]
            ],
            len(items),
        )
        return "\n".join(lines)

    return await run_read(userdata, build)


@function_tool(name="get_account_summary")
async def get_account_summary(ctx: RunContext[SessionUserdata]) -> str:
    """Re-read the logged-in customer's account: balance (or bill due for
    postpaid), active packs with data, minutes and SMS left and their expiry,
    reward points and open support cases. The ACCOUNT SNAPSHOT already has all of
    this and is kept current, so answer from it; call this only right after a
    purchase, recharge or redemption, or when the customer says a figure is wrong.
    """
    return await run_get_account_summary(ctx.userdata)


@function_tool(name="get_usage_breakdown")
async def get_usage_breakdown(
    ctx: RunContext[SessionUserdata], period_days: int = 30, kind: str | None = None
) -> str:
    """Get how much data, voice and SMS the customer used and what it cost.

    Args:
        period_days: Days back, today included: 1 to 90 (1 = today, 7 = this
            week, 30 = this month). Default 30.
        kind: Optional filter: "data", "voice", "sms" or "vas". Leave out for all.
    """
    return await run_get_usage_breakdown(ctx.userdata, period_days, kind)


@function_tool(name="explain_deductions")
async def explain_deductions(ctx: RunContext[SessionUserdata], days: int = 7) -> str:
    """Explain why money left the customer's balance recently: charged usage and
    pack purchases paid from balance. Use it for "why was my balance cut?".

    Args:
        days: How many days back to look, 1 to 90 (default 7).
    """
    return await run_explain_deductions(ctx.userdata, days)
