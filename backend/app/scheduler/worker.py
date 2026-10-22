import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.scheduler.jobs import (
    poll_due_calls,
    process_embedding_jobs,
    sweep_stale_conversations,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scheduler")


async def main() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(poll_due_calls, "interval", seconds=30, id="poll_due_calls")
    scheduler.add_job(
        sweep_stale_conversations,
        "interval",
        minutes=10,
        id="sweep_stale_conversations",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        process_embedding_jobs,
        "interval",
        seconds=5,
        id="process_embedding_jobs",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("scheduler started: cold calls every 30s, embedding jobs every 5s")

    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
