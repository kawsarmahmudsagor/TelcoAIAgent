"""Support tools. Read half: case status."""

from __future__ import annotations

from livekit.agents import RunContext, function_tool

from app.agent.telco_format import format_day
from app.agent.tools._common import run_read
from app.agent.userdata import SessionUserdata
from app.bss import cases

_DETAIL = 3


async def run_get_case_status(userdata: SessionUserdata, ref: str | None = None) -> str:
    def build(db, sid):
        rows = cases.get_case_status(db, sid, ref=ref)
        if not rows:
            return "The customer has no support cases."
        lines = [f"{len(rows)} support case(s):"]
        for c in rows[:_DETAIL]:
            line = (
                f"- {c.ref}: {c.category}, {c.status.value.replace('_', ' ')}, "
                f"opened {format_day(c.created_at)}, last update {format_day(c.updated_at)}"
            )
            if c.resolved_at:
                line += f", resolved {format_day(c.resolved_at)}"
            lines.append(line + f". Issue: {c.description}")
        if len(rows) > _DETAIL:
            lines.append(f"{len(rows) - _DETAIL} more not listed.")
        return "\n".join(lines)

    return await run_read(userdata, build, verify=True)


@function_tool(name="get_case_status")
async def get_case_status(ctx: RunContext[SessionUserdata], ref: str | None = None) -> str:
    """Check the customer's support cases, unresolved ones first.

    Args:
        ref: Optional case number such as "TC-2048"; leave out to list their cases.
    """
    return await run_get_case_status(ctx.userdata, ref)
