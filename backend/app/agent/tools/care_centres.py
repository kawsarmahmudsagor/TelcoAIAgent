"""Care centre finder tool."""

from __future__ import annotations

from livekit.agents import RunContext, function_tool

from app.agent.tools._common import NOT_LOGGED_IN, run_db, subscriber_id_or_none
from app.agent.userdata import SessionUserdata
from app.bss import accounts, care_centres
from app.bss.errors import SubscriberNotFound

TOOL_NAME = "find_care_centre"
ASK_PLACE = "Ask the customer which district or area they are in, then call this again with it."


def _unknown(place: str) -> str:
    return (
        f'"{place}" isn\'t a district or area of Bangladesh I can match. '
        "Ask which district it is in, then call this again with the district."
    )


async def run_find_care_centre(userdata: SessionUserdata, place: str | None = None) -> str:
    place = (place or "").strip()
    if not place:
        sid = subscriber_id_or_none(userdata)
        if sid is None:
            return ASK_PLACE
        try:
            place = await run_db(lambda db: accounts.get_account_summary(db, sid).district)
        except SubscriberNotFound:
            return NOT_LOGGED_IN
    match = care_centres.resolve(place)
    return care_centres.nearest_text(match) if match else _unknown(place)


@function_tool(name=TOOL_NAME)
async def find_care_centre(ctx: RunContext[SessionUserdata], place: str | None = None) -> str:
    """Find the nearest care centre (also asked as customer care, service centre,
    office, branch, store, shop; কাস্টমার কেয়ার, অফিস) with its address and opening
    hours. Defaults to the logged-in customer's district; a guest must name a place.

    Args:
        place: The district or area the customer names, without other words, e.g.
            "Gazipur", "Mirpur", "Cox's Bazar" or "গাজীপুর".
    """
    return await run_find_care_centre(ctx.userdata, place)
