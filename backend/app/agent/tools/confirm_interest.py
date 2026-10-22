from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolError

from app.agent.userdata import SessionUserdata
from app.db.session import SessionLocal
from app.models.call_schedule import CallStatus
from app.repositories import call_schedule_repo


@function_tool()
async def confirm_interest(
    ctx: RunContext[SessionUserdata],
    still_interested: bool,
    reason_if_not: str | None = None,
) -> str:
    """(Outbound cold-call only) Record whether the client is still interested
    in hearing about listings after being contacted proactively. Call this as
    soon as you know the answer, early in the call.

    Args:
        still_interested: True if the client wants to keep talking about listings.
        reason_if_not: Brief reason given, if they're not interested.
    """
    if ctx.userdata.call_schedule_id is None:
        raise ToolError("confirm_interest is only usable during an outbound cold-call session")

    db = SessionLocal()
    try:
        entry = call_schedule_repo.get(db, ctx.userdata.call_schedule_id)
        if entry is None:
            raise ToolError("Could not find the call schedule entry for this session")
        outcome = "interested" if still_interested else f"not interested: {reason_if_not or 'no reason given'}"
        call_schedule_repo.update_fields(
            db,
            entry,
            {
                "outcome": outcome,
                "status": CallStatus.completed if not still_interested else None,
            },
        )
    finally:
        db.close()

    return "Recorded." if still_interested else "Recorded — wrap up the call politely."
