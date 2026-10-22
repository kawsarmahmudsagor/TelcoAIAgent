"""The embedding job runner: claims embedding_jobs rows and does the slow work
(ported from Sellora's jobs.queue + jobs.handlers, sync).

The scheduler process calls `process_pending_jobs` every few seconds in a
worker thread (app.scheduler.jobs.process_embedding_jobs), one batch at a
time (max_instances=1), so the cold-call poller is never delayed by an
embedding call.

Lifecycle of a job:
1. `reset_orphaned_jobs` (once, at scheduler start): anything left
   `processing` belonged to a scheduler that died mid-job, so it goes back to
   `pending`.
2. `claim_next_job`: SELECT ... FOR UPDATE SKIP LOCKED, so a second runner
   would skip a row another one holds instead of running it twice.
3. `run_job`: the handler runs in its own session. Success marks the job
   `succeeded` with stats; any exception marks the job -- and its source, or
   the config's embedding migration -- `failed` with an admin-readable error.

Failures aren't retried automatically (a missing API key would just fail
again every few seconds); POST /api/rag/jobs/{id}/retry re-queues one.

Every source job first purges the source's vectors from every collection and
then embeds it from scratch with the current model and chunk settings, so
ingest, reindex and retry all converge on the same state.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.rag import (
    EmbeddingJob,
    EmbeddingJobStatus,
    EmbeddingJobType,
    RagPageStatus,
    RagSource,
    RagSourcePage,
    RagSourceStatus,
    RagSourceType,
)
from app.rag import index as rag_index
from app.rag.config import RAG_SOURCE_ID_KEY, RAG_SOURCE_PAGE_ID_KEY, collection_for
from app.rag.crawler import CrawlConfig, CrawlError, crawl
from app.rag.ingestion import EmbedTarget, ingest_file, ingest_text, ingest_texts
from app.repositories import agent_config_repo
from app.services import agent_config_service, rag_service
from app.services.agent_config_service import ResolvedAgentConfig

logger = logging.getLogger("rag.jobs")

MAX_ERROR_CHARS = 4000
NO_KEY_MESSAGE = (
    "No OpenRouter API key for embeddings: set OPENROUTER_API_KEY, or save an "
    "OpenRouter key in the dashboard with OpenRouter as the LLM provider"
)


class JobError(RuntimeError):
    """A handler failure with a message fit to show an admin."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def embedding_key(config: ResolvedAgentConfig) -> str:
    """Indirection so tests running with a fake embed model don't need a key."""
    return agent_config_service.embedding_api_key(config)


# --------------------------------------------------------------------------- #
# Queue
# --------------------------------------------------------------------------- #


def reset_orphaned_jobs(db: Session) -> int:
    """Returns every `processing` job (and its source) to `pending`. Only safe
    while no runner is mid-job, i.e. at scheduler startup."""
    ids = list(
        db.scalars(
            update(EmbeddingJob)
            .where(EmbeddingJob.status == EmbeddingJobStatus.processing.value)
            .values(
                status=EmbeddingJobStatus.pending.value,
                started_at=None,
                error="reset to pending after an unclean shutdown",
            )
            .returning(EmbeddingJob.id)
        )
    )
    if ids:
        db.execute(
            update(RagSource)
            .where(
                RagSource.id.in_(
                    select(EmbeddingJob.rag_source_id).where(
                        EmbeddingJob.id.in_(ids), EmbeddingJob.rag_source_id.is_not(None)
                    )
                ),
                RagSource.status == RagSourceStatus.processing.value,
            )
            .values(status=RagSourceStatus.pending.value)
        )
        logger.warning("reset %d orphaned embedding job(s) to pending", len(ids))
    db.commit()
    return len(ids)


def claim_next_job(db: Session, *, commit: bool = True) -> EmbeddingJob | None:
    """Takes the next pending job (lowest priority number, then oldest), or
    returns None. With commit=False the row lock is held until the caller ends
    the transaction (used by the SKIP LOCKED test)."""
    job = db.scalar(
        select(EmbeddingJob)
        .where(EmbeddingJob.status == EmbeddingJobStatus.pending.value)
        .order_by(EmbeddingJob.priority.asc(), EmbeddingJob.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = EmbeddingJobStatus.processing.value
    job.started_at = _now()
    job.finished_at = None
    job.error = None
    job.attempts = (job.attempts or 0) + 1
    if commit:
        db.commit()
    else:
        db.flush()
    return job


def run_job(job_id: uuid.UUID) -> str:
    """Runs one claimed job to completion. Returns its final status."""
    db = SessionLocal()
    try:
        job = db.get(EmbeddingJob, job_id)
        if job is None:  # its source was deleted mid-flight
            return "vanished"
        source = db.get(RagSource, job.rag_source_id) if job.rag_source_id else None
        logger.info("running %s job %s", job.job_type, job_id)
        try:
            stats = dispatch(db, job, source)
            job.status = EmbeddingJobStatus.succeeded.value
            job.finished_at = _now()
            job.error = None
            job.stats = stats or {}
            db.commit()
            logger.info("job %s succeeded: %s", job_id, stats)
            return job.status
        except Exception as exc:
            # The handler may have failed *because* of a DB error; roll back
            # before writing the failure or that write fails too.
            db.rollback()
            return _fail(db, job_id, exc)
    finally:
        db.close()


def _fail(db: Session, job_id: uuid.UUID, exc: BaseException) -> str:
    message = (str(exc) if isinstance(exc, JobError) else f"{type(exc).__name__}: {exc}")
    message = message[:MAX_ERROR_CHARS]
    logger.warning("job %s failed: %s", job_id, message, exc_info=not isinstance(exc, JobError))
    try:
        job = db.get(EmbeddingJob, job_id)
        if job is None:
            return "vanished"
        job.status = EmbeddingJobStatus.failed.value
        job.finished_at = _now()
        job.error = message
        if job.rag_source_id is not None:
            source = db.get(RagSource, job.rag_source_id)
            if source is not None:
                source.status = RagSourceStatus.failed.value
                source.error = message
        if job.job_type == EmbeddingJobType.migrate_embedding.value:
            row = agent_config_repo.get(db)
            if row is not None:
                row.embedding_migration_status = "failed"
                row.embedding_migration_error = message
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("could not record the failure of job %s", job_id)
    return EmbeddingJobStatus.failed.value


def process_pending_jobs(max_jobs: int = 20) -> int:
    """Claims and runs pending jobs one at a time until none are left (or
    `max_jobs` ran). Returns how many ran."""
    processed = 0
    while processed < max_jobs:
        db = SessionLocal()
        try:
            job = claim_next_job(db)
            job_id = job.id if job else None
        finally:
            db.close()
        if job_id is None:
            break
        run_job(job_id)
        processed += 1
    return processed


# --------------------------------------------------------------------------- #
# Handlers
# --------------------------------------------------------------------------- #


def _base_metadata(source: RagSource) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        RAG_SOURCE_ID_KEY: str(source.id),
        "rag_source_name": source.name,
        "rag_source_type": source.source_type,
    }
    if source.source_url:
        metadata["source_url"] = source.source_url
    if source.filename:
        metadata["filename"] = source.filename
    return metadata


def _target(config: ResolvedAgentConfig, embedding_model: str, api_key: str) -> EmbedTarget:
    return EmbedTarget(
        collection=collection_for(embedding_model),
        embedding_model=embedding_model,
        api_key=api_key,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )


def _crawl_and_embed(db: Session, source: RagSource, target: EmbedTarget) -> tuple[int, dict]:
    if not source.source_url:
        raise JobError("This link source has no URL")
    settings = source.config or {}
    crawl_config = CrawlConfig(
        max_depth=settings.get("max_depth", 1),
        max_pages=settings.get("max_pages", 25),
        allowed_domains=tuple(settings.get("allowed_domains") or ()),
    )
    try:
        # The crawler is async (httpx); this runs in a worker thread, which
        # has no event loop of its own.
        result = asyncio.run(crawl(source.source_url, crawl_config))
    except CrawlError as exc:
        raise JobError(str(exc)) from exc
    if not result.pages:
        raise JobError(
            f"Crawling {source.source_url} found no usable pages "
            f"({len(result.skipped)} skipped, {len(result.errors)} error(s))"
        )

    # A re-crawl can find a different set of pages, so the old ones go.
    db.execute(sql_delete(RagSourcePage).where(RagSourcePage.rag_source_id == source.id))
    db.flush()
    db.expire(source, ["pages"])

    total = 0
    failed = 0
    for page in result.pages:
        row = RagSourcePage(
            id=uuid.uuid4(),
            rag_source_id=source.id,
            url=page.url,
            normalized_url=page.normalized_url,
            title=page.title,
            depth=page.depth,
            status=RagPageStatus.processing.value,
            checksum=page.content_checksum,
        )
        row.chroma_doc_id = f"{source.id}:{row.id}"
        db.add(row)
        metadata = {
            **_base_metadata(source),
            RAG_SOURCE_PAGE_ID_KEY: str(row.id),
            "page_url": page.url,
            "page_title": page.title or "",
        }
        try:
            chunks = ingest_text(page.text, row.chroma_doc_id, target, metadata=metadata)
        except Exception as exc:
            # One unembeddable page mustn't lose the others.
            logger.warning("could not embed %s: %s", page.url, exc)
            row.status = RagPageStatus.failed.value
            row.error = str(exc)[:2000]
            failed += 1
            continue
        row.status = RagPageStatus.ready.value
        row.chunk_count = chunks
        total += chunks
    db.flush()

    if total == 0:
        raise JobError(
            f"Crawled {len(result.pages)} page(s) from {source.source_url} but none could be "
            "embedded (see the page errors)"
        )
    source.config = {**(source.config or {}), "last_crawl": result.stats()}
    return total, {**result.stats(), "failed_pages": failed}


def embed_source(db: Session, source: RagSource, target: EmbedTarget) -> tuple[int, dict]:
    """Embeds a source's content into `target`. Returns (chunks, stats).
    Doesn't purge anything except the doc ids it rewrites."""
    metadata = _base_metadata(source)
    if source.source_type == RagSourceType.document.value:
        path = rag_service.source_file_path(source)
        if path is None or not path.exists():
            raise JobError(f"The uploaded file for {source.name!r} is missing")
        try:
            chunks = ingest_file(path, source.chroma_doc_id, target, metadata=metadata)
        except ValueError as exc:
            raise JobError(str(exc)) from exc
        return chunks, {"chunks": chunks, "file": path.name}

    if source.source_type == RagSourceType.text.value:
        if not (source.content or "").strip():
            raise JobError("This text source is empty")
        chunks = ingest_text(source.content, source.chroma_doc_id, target, metadata=metadata)
        return chunks, {"chunks": chunks}

    if source.source_type == RagSourceType.link.value:
        chunks, stats = _crawl_and_embed(db, source, target)
        return chunks, {**stats, "chunks": chunks}

    raise JobError(f"Unsupported source type {source.source_type!r}")


def _mark_ready(source: RagSource, chunks: int, target: EmbedTarget) -> None:
    source.status = RagSourceStatus.ready.value
    source.chunk_count = chunks
    source.error = None
    source.last_indexed_at = _now()
    source.embedding_model = target.embedding_model
    source.collection = target.collection


def handle_source_job(
    db: Session, source: RagSource, config: ResolvedAgentConfig, api_key: str
) -> dict[str, Any]:
    """ingest / crawl / reindex: purge the source's vectors
    everywhere, then embed it with the current model and chunk settings."""
    target = _target(config, config.embedding_model, api_key)
    removed = rag_index.delete_where({RAG_SOURCE_ID_KEY: str(source.id)})
    chunks, stats = embed_source(db, source, target)
    _mark_ready(source, chunks, target)
    return {**stats, "chunks_removed": removed}


def handle_delete(db: Session, source: RagSource) -> dict[str, Any]:
    """Unpublishes a source but keeps its row (status disabled)."""
    removed = rag_index.delete_where({RAG_SOURCE_ID_KEY: str(source.id)})
    source.status = RagSourceStatus.disabled.value
    source.chunk_count = 0
    return {"chunks_removed": removed}


def handle_migration(
    db: Session, job: EmbeddingJob, config: ResolvedAgentConfig, api_key: str
) -> dict[str, Any]:
    """Re-embeds every source into the target model's collection while the old
    one keeps serving, then flips agent_config.embedding_model and drops the
    old collection. If any source fails, nothing flips: the partial target
    collection is dropped and the migration is marked failed."""
    target_model = (job.payload or {}).get("target")
    if not target_model:
        raise JobError("The migration job has no target model")
    old_model = config.embedding_model
    target = _target(config, target_model, api_key)

    sources = db.scalars(
        select(RagSource)
        .where(RagSource.status != RagSourceStatus.disabled.value)
        .order_by(RagSource.created_at)
    ).all()
    chunks_by_source: dict[uuid.UUID, int] = {}
    failures: list[str] = []
    for source in sources:
        try:
            rag_index.delete_where({RAG_SOURCE_ID_KEY: str(source.id)}, [target.collection])
            chunks_by_source[source.id], _stats = embed_source(db, source, target)
        except Exception as exc:
            logger.warning("migration: could not re-embed %s: %s", source.name, exc)
            failures.append(f"{source.name}: {exc}")

    if failures:
        try:
            rag_index.drop_collection(target.collection)
        except Exception:
            logger.exception("could not drop the partial collection %s", target.collection)
        raise JobError(
            f"{len(failures)} of {len(sources)} source(s) could not be re-embedded with "
            f"{target_model}, so the knowledge base stays on {old_model}. "
            + "; ".join(failures)[:3000]
        )

    for source in sources:
        _mark_ready(source, chunks_by_source[source.id], target)
    row = agent_config_repo.get_or_create(db)
    row.embedding_model = target_model
    row.embedding_migration_status = "succeeded"
    row.embedding_migration_target = None
    row.embedding_migration_error = None
    db.commit()

    old_collection = collection_for(old_model)
    if old_collection != target.collection:
        try:
            rag_index.drop_collection(old_collection)
        except Exception:
            logger.exception("could not drop the old collection %s", old_collection)
    return {
        "sources": len(sources),
        "chunks": sum(chunks_by_source.values()),
        "from": old_model,
        "to": target_model,
    }


def dispatch(db: Session, job: EmbeddingJob, source: RagSource | None) -> dict[str, Any]:
    config = agent_config_service.resolve(agent_config_repo.get(db))
    job_type = job.job_type

    if job_type == EmbeddingJobType.delete.value:
        if source is None:
            raise JobError("The job's source no longer exists")
        return handle_delete(db, source)

    api_key = embedding_key(config)
    if not api_key:
        raise JobError(NO_KEY_MESSAGE)

    if job_type == EmbeddingJobType.migrate_embedding.value:
        return handle_migration(db, job, config, api_key)

    if job_type not in {
        EmbeddingJobType.ingest.value,
        EmbeddingJobType.crawl.value,
        EmbeddingJobType.reindex.value,
    }:
        raise JobError(f"Unknown job type {job_type!r}")
    if source is None:
        raise JobError("The job's source no longer exists")

    # Committed so the dashboard sees `processing` while the embedding runs.
    source.status = RagSourceStatus.processing.value
    db.commit()
    return handle_source_job(db, source, config, api_key)
