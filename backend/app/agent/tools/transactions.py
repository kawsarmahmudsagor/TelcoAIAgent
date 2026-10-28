"""Transaction history lookup."""

from __future__ import annotations

from livekit.agents import RunContext, function_tool

from app.agent.telco_format import format_amount, format_day
from app.agent.tools._common import LISTED, listed, parse_enum, run_read
from app.agent.userdata import SessionUserdata
from app.bss import transactions
from app.models.telco import TxnStatus, TxnType


async def run_lookup_transactions(
    userdata: SessionUserdata,
    type: str | None = None,
    status: str | None = None,
    ref: str | None = None,
    days: int = 30,
) -> str:
    def build(db, sid):
        filters = dict(
            type=parse_enum(TxnType, type), status=parse_enum(TxnStatus, status), ref=ref, days=days
        )
        rows = transactions.lookup(db, sid, limit=LISTED, **filters)
        if not rows:
            return "No matching transactions found."
        total = transactions.count(db, sid, **filters)
        lines = [f"{total} transactions, newest first:"]
        found = []
        for t in rows:
            # The type word appears once: "purchase <package>, ৳ 120" or
            # "recharge of ৳ 200".
            if t.package_name:
                head = f"{t.type.value} {t.package_name}, {format_amount(t.amount)}"
            else:
                head = f"{t.type.value} of {format_amount(t.amount)}"
            if t.points_earned:
                head += f", earned {t.points_earned} points"
            line = (
                f"- {t.ref}: {head} via "
                f"{t.channel.value}, {t.status.value}, {format_day(t.created_at, with_time=True)}"
            )
            if t.target_msisdn:
                line += f", to {t.target_msisdn[:3]}••••{t.target_msisdn[-4:]}"
            if t.failure_reason:
                line += f", failure reason: {t.failure_reason}"
            found.append(line + ".")
        lines += listed(found, total)
        return "\n".join(lines)

    return await run_read(userdata, build, verify=True)


@function_tool(name="lookup_transactions")
async def lookup_transactions(
    ctx: RunContext[SessionUserdata],
    type: str | None = None,
    status: str | None = None,
    ref: str | None = None,
    days: int = 30,
) -> str:
    """Look up the customer's recharges, package purchases and redemptions.
    Use it to confirm a payment or find a failed one.

    Args:
        type: Optional: "recharge", "purchase" or "redeem".
        status: Optional: "success", "pending" or "failed".
        ref: Optional transaction reference such as "TXN-840221" (or just its
            digits); ignores days.
        days: How many days back to look (default 30).
    """
    return await run_lookup_transactions(ctx.userdata, type, status, ref, days)
