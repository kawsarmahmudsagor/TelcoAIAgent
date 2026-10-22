from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from app.agent.tools._datetime import parse_future_local
from app.agent.userdata import SessionUserdata
from app.db.session import SessionLocal
from app.models.call_schedule import CallStatus
from app.repositories import call_schedule_repo


@function_tool()
async def schedule_followup(
    ctx: RunContext[SessionUserdata],
    follow_up_date: str,
    note: str,
) -> str:
    """(Outbound cold-call only) If the client would rather be contacted again
    later instead of right now, schedule a new future cold-call and end the
    current call politely.

    Args:
        follow_up_date: Local ISO 8601 date/time to call back, e.g. "2026-09-01T10:00:00".
        note: Brief note on why/what to follow up about.
    """
    if ctx.userdata.client is None or ctx.userdata.call_schedule_id is None:
        raise ToolError("schedule_followup is only usable during an outbound cold-call session")

    when = parse_future_local(follow_up_date, "follow_up_date")

    db = SessionLocal()
    try:
        entry = call_schedule_repo.get(db, ctx.userdata.call_schedule_id)
        # A follow-up to a phone call rings the same phone.
        call_schedule_repo.create(
            db,
            client_id=ctx.userdata.client.id,
            scheduled_at=when,
            dial_number=entry.dial_number if entry is not None else None,
        )
        if entry is not None:
            call_schedule_repo.update_fields(
                db, entry, {"outcome": f"follow-up requested: {note}", "status": CallStatus.completed}
            )
    finally:
        db.close()

    return f"Follow-up scheduled for {when.isoformat()}. Wrap up the call politely."
