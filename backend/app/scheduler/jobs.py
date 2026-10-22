import asyncio
import json
import logging
from datetime import timedelta

from livekit.api import CreateRoomRequest, LiveKitAPI, RoomAgentDispatch
from psycopg.errors import UndefinedTable
from sqlalchemy.exc import ProgrammingError

from app.config import get_settings
from app.db.session import SessionLocal
from app.models.call_schedule import CallScheduleEntry, CallStatus
from app.rag import jobs as rag_jobs
from app.repositories import call_schedule_repo, conversation_repo
from app.services.livekit_rooms import delete_room

logger = logging.getLogger("scheduler")


async def _dispatch_call(entry: CallScheduleEntry) -> None:
    settings = get_settings()
    room_name = f"coldcall-{entry.id}"
    metadata = json.dumps(
        {
            "channel": "outbound_coldcall",
            "client_id": str(entry.client_id),
            "call_schedule_id": str(entry.id),
            # Set -> the agent dials this phone via SIP instead of waiting for
            # the dashboard's browser to join (see app.agent.phone_dial).
            "dial_number": entry.dial_number,
        }
    )

    lk = LiveKitAPI(
        url=settings.livekit_url, api_key=settings.livekit_api_key, api_secret=settings.livekit_api_secret
    )
    try:
        await lk.room.create_room(
            CreateRoomRequest(
                name=room_name,
                agents=[RoomAgentDispatch(agent_name=settings.agent_name, metadata=metadata)],
            )
        )
    finally:
        await lk.aclose()

    db = SessionLocal()
    try:
        went_live = call_schedule_repo.transition(
            db,
            entry.id,
            from_statuses={CallStatus.dispatched},
            values={"livekit_room_name": room_name, "status": CallStatus.in_progress},
        )
    finally:
        db.close()
    if not went_live:
        # Declined/cancelled while the room was being created -- don't leave the
        # agent waiting in a room nobody will join.
        await delete_room(room_name)


async def poll_due_calls() -> None:
    """Claims due `call_schedule` rows and dispatches a LiveKit room + agent
    for each. Runs on an interval via APScheduler (see worker.py)."""
    db = SessionLocal()
    try:
        due_entries = call_schedule_repo.claim_due_entries(db, limit=5)
    finally:
        db.close()

    for entry in due_entries:
        try:
            await _dispatch_call(entry)
            logger.info("dispatched cold call for call_schedule=%s", entry.id)
        except Exception:
            logger.exception("failed to dispatch cold call for call_schedule=%s", entry.id)
            db = SessionLocal()
            try:
                call_schedule_repo.transition(
                    db,
                    entry.id,
                    from_statuses={CallStatus.dispatched, CallStatus.in_progress},
                    values={"status": CallStatus.failed, "outcome": "dispatch failed"},
                )
            finally:
                db.close()


# A conversation still "active" this long after its last message lost its agent
# worker (crash/kill) before the shutdown callback could close it.
STALE_CONVERSATION_IDLE = timedelta(hours=2)


def _sweep_stale_conversations() -> int:
    db = SessionLocal()
    try:
        return conversation_repo.end_stale(db, idle_for=STALE_CONVERSATION_IDLE)
    finally:
        db.close()


async def sweep_stale_conversations() -> None:
    """Marks conversations left `active` by a crashed worker as ended. Runs on
    an interval via APScheduler (see worker.py)."""
    ended = await asyncio.to_thread(_sweep_stale_conversations)
    if ended:
        logger.info("ended %d stale conversation(s)", ended)


# Orphaned `processing` jobs are reset once, before this process runs any job.
# Done lazily on the first tick rather than at startup, and retried every tick
# until it works: in Docker the scheduler can start before the api container
# has run the migrations, so embedding_jobs may not exist yet.
_orphans_reset = False
_waiting_for_table_logged = False


def _process_embedding_jobs() -> int:
    global _orphans_reset, _waiting_for_table_logged
    db = SessionLocal()
    try:
        if not _orphans_reset:
            rag_jobs.reset_orphaned_jobs(db)
            _orphans_reset = True
    except ProgrammingError as exc:
        db.rollback()
        if isinstance(exc.orig, UndefinedTable):
            if not _waiting_for_table_logged:
                logger.warning("embedding_jobs table missing (migrations not run yet?); will retry")
                _waiting_for_table_logged = True
            return 0
        raise
    finally:
        db.close()
    return rag_jobs.process_pending_jobs()


async def process_embedding_jobs() -> None:
    """Runs pending knowledge-base embedding jobs. The whole batch runs in a
    worker thread so poll_due_calls is never held up by an embedding call;
    APScheduler's max_instances=1 keeps it to one batch at a time."""
    try:
        processed = await asyncio.to_thread(_process_embedding_jobs)
    except Exception:
        logger.exception("embedding job processing failed")
        return
    if processed:
        logger.info("processed %d embedding job(s)", processed)
