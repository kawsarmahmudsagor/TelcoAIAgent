import asyncio
import logging
from datetime import timedelta

from psycopg.errors import UndefinedTable
from sqlalchemy.exc import ProgrammingError

from app.db.session import SessionLocal
from app.rag import jobs as rag_jobs
from app.repositories import conversation_repo

logger = logging.getLogger("scheduler")


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
    worker thread so the event loop is never held up by an embedding call;
    APScheduler's max_instances=1 keeps it to one batch at a time."""
    try:
        processed = await asyncio.to_thread(_process_embedding_jobs)
    except Exception:
        logger.exception("embedding job processing failed")
        return
    if processed:
        logger.info("processed %d embedding job(s)", processed)
