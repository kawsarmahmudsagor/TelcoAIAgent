"""Network status tool."""

from __future__ import annotations

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from app.agent.telco_format import format_day
from app.agent.tools._common import (
    LISTED,
    NOT_LOGGED_IN,
    error_text,
    listed,
    run_db,
    subscriber_id_or_none,
)
from app.agent.userdata import SessionUserdata
from app.bss import accounts, care_centres, network
from app.bss.errors import BssError, SubscriberNotFound

ASK_DISTRICT = "Ask the customer which district they are in, then call this again with it."


def _unknown(place: str) -> str:
    return (
        f'"{place}" isn\'t a district or area of Bangladesh I can match. '
        "Ask which district it is in, then call this again with the district."
    )


async def run_check_network_status(userdata: SessionUserdata, district: str | None = None) -> str:
    sid = subscriber_id_or_none(userdata)
    place = (district or "").strip()
    if not place and sid is None:
        return ASK_DISTRICT

    def build(db):
        # Incidents are filed by English district: "সিলেট" or an area such as
        # "Tongi" (Gazipur) found none and read as all clear.
        area = None
        if not place:
            where = accounts.get_account_summary(db, sid).district
        elif (match := care_centres.resolve(place)) is not None:
            where = match.district
            area = match.place if match.place != match.district else None
        else:
            where = place
        incidents = network.check_network_status(db, where)
        in_area = f" ({area} is in {where})" if area else ""
        if not incidents:
            if place and where == place:
                return _unknown(place)
            return f"No network problems or planned work reported in {where}{in_area}."
        if area:
            # The named area's own incidents first.
            incidents.sort(key=lambda i: area.lower() not in i.area.lower())
        lines = [f"{len(incidents)} network incident(s) in {where}{in_area}:"]
        found = []
        for i in incidents[:LISTED]:
            ends = f", expected until {format_day(i.ends_at, with_time=True)}" if i.ends_at else ""
            found.append(
                f"- {i.area}: {i.kind.value}, {i.status.value}, since "
                f"{format_day(i.starts_at, with_time=True)}{ends}. {i.message}"
            )
        lines += listed(found, len(incidents))
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
        district: Optional district or area the customer names, English or
            Bangla, such as "Dhaka", "Mirpur", "Tongi" or "সিলেট".
    """
    return await run_check_network_status(ctx.userdata, district)
