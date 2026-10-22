"""Recharge tool (OTP-gated): the customer's own number or another one."""

from __future__ import annotations

from decimal import Decimal

from livekit.agents import RunContext, function_tool

from app.agent import actions
from app.agent.tools._common import parse_enum, run_write
from app.agent.userdata import SessionUserdata
from app.bss.errors import InvalidRequest
from app.bss.types import RechargeRequest
from app.models.telco import TxnChannel


async def run_start_recharge(
    userdata: SessionUserdata, amount: float, channel: str, msisdn: str | None = None
) -> str:
    async def call() -> str:
        pay = parse_enum(TxnChannel, channel)
        if pay is None:
            raise InvalidRequest("channel is required")
        req = RechargeRequest(amount=Decimal(str(amount)), channel=pay, target_msisdn=msisdn or None)
        return await actions.start_action(userdata, "recharge", req)

    return await run_write(userdata, call)


@function_tool(name="start_recharge")
async def start_recharge(
    ctx: RunContext[SessionUserdata], amount: float, channel: str, msisdn: str | None = None
) -> str:
    """Start a recharge. Nothing is charged yet: this quotes it and sends a
    6-digit code to the customer's screen; the recharge happens only after
    verify_otp (or the Confirm button) succeeds. 20 to 1000 taka per recharge.

    Args:
        amount: Amount in taka.
        channel: How they pay: "bkash", "nagad" or "card".
        msisdn: Another number to recharge (11 digits, starting 01); leave out for their own.
    """
    return await run_start_recharge(ctx.userdata, amount, channel, msisdn)
