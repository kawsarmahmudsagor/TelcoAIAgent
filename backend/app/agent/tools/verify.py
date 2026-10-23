"""Confirming or cancelling the pending write by voice or text."""

from __future__ import annotations

from livekit.agents import RunContext, function_tool

from app.agent import actions
from app.agent.tools._common import run_write
from app.agent.userdata import SessionUserdata


async def run_verify_otp(userdata: SessionUserdata, code: str) -> str:
    return await run_write(userdata, lambda: actions.confirm_action(userdata, code))


async def run_cancel_pending_action(userdata: SessionUserdata) -> str:
    async def call() -> str:
        had_case = userdata.pending_case is not None
        userdata.pending_case = None
        if userdata.pending_action is None and had_case:
            return "The drafted support case was cancelled; nothing was opened."
        text = await actions.cancel_action(userdata)
        if had_case:
            text += " The drafted support case was cancelled too."
        return text

    return await run_write(userdata, call)


@function_tool(name="verify_otp")
async def verify_otp(ctx: RunContext[SessionUserdata], code: str) -> str:
    """Confirm the pending purchase, recharge or redemption with the 6-digit
    code the customer says or types. Only report success if this returns it.

    Args:
        code: The code exactly as the customer gave it (any digits or script).
    """
    return await run_verify_otp(ctx.userdata, code)


@function_tool(name="cancel_pending_action")
async def cancel_pending_action(ctx: RunContext[SessionUserdata]) -> str:
    """Cancel the purchase, recharge or redemption waiting for a code, or a
    support case being drafted, when the customer says they do not want it."""
    return await run_cancel_pending_action(ctx.userdata)
