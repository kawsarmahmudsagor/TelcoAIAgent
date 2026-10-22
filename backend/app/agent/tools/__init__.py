from app.agent.tools.book_appointment import book_appointment
from app.agent.tools.booking_form import update_booking_form
from app.agent.tools.confirm_interest import confirm_interest
from app.agent.tools.schedule_followup import schedule_followup

ALL_TOOLS = [
    update_booking_form,
    book_appointment,
    confirm_interest,
    schedule_followup,
]
# confirm_interest / schedule_followup only work against a cold call's lead and
# call_schedule row -- offering them on inbound just invites failed calls.
INBOUND_TOOLS = [update_booking_form, book_appointment]

__all__ = [
    "ALL_TOOLS",
    "INBOUND_TOOLS",
    "update_booking_form",
    "book_appointment",
    "confirm_interest",
    "schedule_followup",
]
