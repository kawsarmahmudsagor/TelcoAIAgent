"""Reward tools. Read half: points and the offers the customer qualifies for."""

from __future__ import annotations

from livekit.agents import RunContext, function_tool

from app.agent.telco_format import format_amount
from app.agent.tools._common import run_read
from app.agent.userdata import SessionUserdata
from app.bss import rewards


async def run_get_offers_and_points(userdata: SessionUserdata) -> str:
    def build(db, sid):
        res = rewards.get_offers_and_points(db, sid)
        userdata.offer_ids = [o.id for o in res.offers]
        lines = [f"Reward points: {res.reward_points}."]
        if not res.offers:
            lines.append("No offers available for them right now.")
            return "\n".join(lines)
        lines.append("Offers (numbered; the customer may refer to them by number):")
        for n, o in enumerate(res.offers, 1):
            bits = [o.title]
            if o.description:
                bits.append(o.description)
            if o.points_cost is not None:
                bits.append(f"costs {o.points_cost} points")
            if o.cashback_percent is not None:
                cb = f"{o.cashback_percent.normalize():f}% cashback"
                if o.cashback_cap is not None:
                    cb += f" up to {format_amount(o.cashback_cap)}"
                if o.min_recharge is not None:
                    cb += f" on recharges of {format_amount(o.min_recharge)} or more"
                bits.append(cb)
            if o.package is not None:
                bits.append(f"pack {o.package.name} at {format_amount(o.package.price)}")
            if o.ends_on is not None:
                bits.append(f"ends {o.ends_on.day} {o.ends_on:%B}")
            lines.append(f"#{n} " + "; ".join(bits) + ".")
        return "\n".join(lines)

    return await run_read(userdata, build)


@function_tool(name="get_offers_and_points")
async def get_offers_and_points(ctx: RunContext[SessionUserdata]) -> str:
    """Get the customer's reward points and the offers they can use now,
    numbered #1, #2... so "the second one" can be resolved later."""
    return await run_get_offers_and_points(ctx.userdata)
