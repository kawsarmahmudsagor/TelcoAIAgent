"""Reward tools: points and the offers the customer qualifies for, and
redeeming one by its number in that list (OTP-gated)."""

from __future__ import annotations

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from app.agent import actions
from app.agent.telco_format import format_amount
from app.agent.tools._common import NOT_LOGGED_IN, run_read, run_write
from app.agent.userdata import SessionUserdata
from app.bss import rewards


async def run_get_offers_and_points(userdata: SessionUserdata) -> str:
    def build(db, sid):
        res = rewards.get_offers_and_points(db, sid)
        userdata.offer_ids = [o.id for o in res.offers]
        lines = [
            f"Reward points: {res.reward_points}.",
            "Earning: every recharge earns the payer 1 point per full ৳10 "
            "(৳45 earns 4; the leftover taka earns nothing and is not carried over).",
        ]
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


async def run_redeem_reward(userdata: SessionUserdata, offer_number: int) -> str:
    if userdata.subscriber_id is None:
        return NOT_LOGGED_IN
    if not 1 <= offer_number <= len(userdata.offer_ids):
        raise ToolError(
            f"There is no offer #{offer_number} in the last list. "
            "Call get_offers_and_points first, then use its numbers."
        )
    offer_id = userdata.offer_ids[offer_number - 1]
    return await run_write(userdata, lambda: actions.start_action(userdata, "redeem", offer_id))


@function_tool(name="get_offers_and_points")
async def get_offers_and_points(ctx: RunContext[SessionUserdata]) -> str:
    """Get the customer's reward points and the offers they can use now,
    numbered #1, #2... so "the second one" can be resolved later."""
    return await run_get_offers_and_points(ctx.userdata)


@function_tool(name="redeem_reward")
async def redeem_reward(ctx: RunContext[SessionUserdata], offer_number: int) -> str:
    """Start redeeming reward points for an offer. Nothing is spent yet: this
    sends a 6-digit code to the customer's screen; the redemption happens only
    after verify_otp (or the confirm card, with the code) succeeds.

    Args:
        offer_number: The offer's number (#1, #2...) from get_offers_and_points.
    """
    return await run_redeem_reward(ctx.userdata, offer_number)
