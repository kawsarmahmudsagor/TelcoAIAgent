from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from app.agent import booking
from app.agent.userdata import SessionUserdata

@function_tool()
async def update_booking_form(
    ctx: RunContext[SessionUserdata],
    listing_number: int | None = None,
    proposed_datetime: str | None = None,
    full_name: str | None = None,
    phone: str | None = None,
) -> str:
    """Fill in the viewing booking form. Call it as soon as the customer wants a
    viewing, and again whenever they give or change a detail; pass only what they
    said in this conversation and leave the rest as None. It tells you what's still
    missing, and when the form is complete, to read it back and ask them to confirm.
    Never ask for an email address.

    Args:
        listing_number: The #number search_apartments gave the listing to view.
        proposed_datetime: Local ISO 8601 date/time for the viewing, e.g. "2026-08-25T15:00:00".
        full_name: The customer's name, as they gave it.
        phone: The customer's mobile number, exactly as they said or typed it.
    """
    userdata = ctx.userdata
    pending = booking.open_form(userdata)
    errors = booking.merge(
        userdata,
        pending,
        listing_number=listing_number,
        proposed_datetime=proposed_datetime,
        full_name=full_name,
        phone=phone,
    )
    await booking.push_state(userdata, userdata.room, pending, errors)
    if errors:
        problems = " ".join(f"{field}: {message}" for field, message in errors.items())
        raise ToolError(
            f"Not saved -- {problems} Every other detail was saved. Ask the customer for the "
            "rejected one again, then call update_booking_form with it."
        )
    return booking.next_step(pending, is_phone_call=userdata.is_phone_call)
