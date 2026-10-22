from livekit.agents import RunContext, function_tool

from app.agent import booking
from app.agent.userdata import SessionUserdata


@function_tool()
async def book_appointment(ctx: RunContext[SessionUserdata]) -> str:
    """Book the viewing on the booking form, as it was last read back to the
    customer. Call it only after update_booking_form said the form is complete,
    you read the name, phone number, property and time back to the customer, and
    they clearly said yes. It takes no arguments: to change a detail, call
    update_booking_form instead.
    """
    return await booking.confirm_booking(ctx.userdata, ctx.userdata.room)
