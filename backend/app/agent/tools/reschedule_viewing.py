import asyncio
from datetime import datetime

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from app.agent.tools._datetime import check_viewing_hours, parse_future_local, spoken_local
from app.agent.userdata import SessionUserdata
from app.config import get_settings
from app.db.session import SessionLocal
from app.repositories import booking_repo, call_schedule_repo, client_repo
from app.services import mock_email_service


def _move(userdata: SessionUserdata, when: datetime) -> None:
    """The database part (runs in a worker thread)."""
    viewing = userdata.upcoming_viewing
    db = SessionLocal()
    try:
        moved = booking_repo.update_time(db, viewing.booking_id, when)
        if moved is None:
            raise ToolError(
                "That viewing was cancelled, so it can't be moved. Tell the customer and offer "
                "to book a new one."
            )
        booking, old_when = moved
        client = client_repo.get(db, booking.client_id)
        mock_email_service.send_invite(
            db,
            booking_id=booking.id,
            client_name=client.full_name if client is not None else "the customer",
            client_email=client.email if client is not None else None,
            client_phone=client.phone if client is not None else None,
            ceo_email=get_settings().ceo_email,
            property_title=viewing.property_title,
            when=when,
            rescheduled_from=old_when,
        )
        entry = call_schedule_repo.get(db, userdata.call_schedule_id)
        if entry is not None:
            call_schedule_repo.update_fields(
                db, entry, {"outcome": f"viewing moved to {spoken_local(when)}"}
            )
    finally:
        db.close()


@function_tool()
async def reschedule_viewing(ctx: RunContext[SessionUserdata], new_datetime: str) -> str:
    """(Viewing follow-up calls only) Move the customer's booked viewing to a new
    day and time they asked for. Their name and number are already on file.

    Args:
        new_datetime: Local ISO 8601 date/time of the viewing, e.g. "2026-09-01T10:00:00".
    """
    userdata = ctx.userdata
    if userdata.upcoming_viewing is None or userdata.call_schedule_id is None:
        raise ToolError("reschedule_viewing is only usable on a call following up a viewing")
    when = parse_future_local(new_datetime, "new_datetime")
    check_viewing_hours(when, "new_datetime")
    await asyncio.to_thread(_move, userdata, when)
    userdata.upcoming_viewing.when = when
    return (
        f"Viewing moved to {spoken_local(when)}. Tell the customer the new day and time, "
        'speaking to them as "you".'
    )
