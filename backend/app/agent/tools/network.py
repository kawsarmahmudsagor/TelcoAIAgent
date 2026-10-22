"""Network status tool."""

from __future__ import annotations

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from app.agent.telco_format import format_day
from app.agent.tools._common import NOT_LOGGED_IN, error_text, run_db, subscriber_id_or_none
from app.agent.userdata import SessionUserdata
from app.bss import accounts, network
from app.bss.errors import BssError, SubscriberNotFound

ASK_DISTRICT = "Ask the customer which district they are in, then call this again with it."
_DETAIL = 3


async def run_check_network_status(userdata: SessionUserdata, district: str | None = None) -> str:
    sid = subscriber_id_or_none(userdata)
    if not district and sid is None:
        return ASK_DISTRICT

    def build(db):
        where = district or accounts.get_account_summary(db, sid).district
        incidents = network.check_network_status(db, where)
        if not incidents:
            return f"No network problems or planned work reported in {where}."
        lines = [f"{len(incidents)} network incident(s) in {where}:"]
        for i in incidents[:_DETAIL]:
            ends = f", expected until {format_day(i.ends_at, with_time=True)}" if i.ends_at else ""
            lines.append(
                f"- {i.area}: {i.kind.value}, {i.status.value}, since "
                f"{format_day(i.starts_at, with_time=True)}{ends}. {i.message}"
            )
        if len(incidents) > _DETAIL:
            lines.append(f"{len(incidents) - _DETAIL} more not listed.")
        return "\n".join(lines)

    try:
        return await run_db(build)
    except SubscriberNotFound:
        return NOT_LOGGED_IN
    except BssError as err:
        raise ToolError(error_text(err)) from err


@function_tool(name="check_network_status")
async def check_network_status(ctx: RunContext[SessionUserdata], district: str | None = None) -> str:
    """Check for outages, congestion or planned maintenance. Defaults to the
    logged-in customer's district; a guest must name one.

    Args:
        district: Optional district name such as "Dhaka" or "Chattogram".
    """
    return await run_check_network_status(ctx.userdata, district)
