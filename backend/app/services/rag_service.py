"""CRUD and orchestration for knowledge-base sources and their jobs (ported
from Sellora's rag_service, sync).

This module does the cheap, synchronous part -- validate an upload, store the
file, insert the rag_sources row, queue an embedding_jobs row -- and returns
at once, so the dashboard shows a `pending` source immediately. The scheduler's
job runner (app.rag.jobs) does the slow part and is the only thing that moves a
source to `ready` or `failed`.

Delete is the exception and runs inline: embedding_jobs.rag_source_id cascades,
so a queued cleanup job would be deleted with the very row it cleans up after.
"""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models.agent_config import DEFAULT_EMBEDDING_MODEL
from app.models.rag import (
    EmbeddingJob,
    EmbeddingJobStatus,
    EmbeddingJobType,
    RagSource,
    RagSourceStatus,
    RagSourceType,
)
from app.rag import index as rag_index
from app.rag.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, RAG_SOURCE_ID_KEY, collection_for
from app.rag.crawler import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES, MAX_DEPTH_CAP, MAX_PAGES_CAP
from app.rag.net import UnsafeURLError, assert_scheme_and_host
from app.repositories import agent_config_repo

logger = logging.getLogger("rag.service")

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_OPEN_JOB_STATUSES = (EmbeddingJobStatus.pending.value, EmbeddingJobStatus.processing.value)
# Sources whose vectors are served (stale = old chunking, still valid vectors).
SEARCHABLE_STATUSES = (RagSourceStatus.ready.value, RagSourceStatus.stale.value)


class RagServiceError(ValueError):
    """A caller error (bad upload, bad URL). Routes turn it into a 4xx."""


class NotFoundError(RagServiceError):
    pass


class ConflictError(RagServiceError):
    pass


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def upload_root() -> Path:
    return get_settings().upload_path


def source_file_path(source: RagSource) -> Path | None:
    if not source.storage_path:
        return None
    return (upload_root() / source.storage_path).resolve()


def safe_filename(filename: str, *, fallback: str = "upload") -> str:
    """A filesystem-safe basename: no directories, no surprises."""
    name = Path(filename or "").name
    cleaned = _UNSAFE_FILENAME.sub("_", name).strip("._")
    return cleaned[:180] or fallback


def _remove_source_files(source_id: uuid.UUID) -> None:
    directory = upload_root() / "rag" / str(source_id)
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #


def current_embedding_model(db: Session) -> str:
    row = agent_config_repo.get(db)
    return (row.embedding_model if row else None) or DEFAULT_EMBEDDING_MODEL


def enqueue_job(
    db: Session,
    job_type: EmbeddingJobType,
    *,
    rag_source_id: uuid.UUID | None = None,
    payload: dict | None = None,
    priority: int = 0,
) -> EmbeddingJob:
    """Queues one job (flushes, doesn't commit)."""
    job = EmbeddingJob(
        job_type=job_type.value,
        rag_source_id=rag_source_id,
        payload=payload or {},
        priority=priority,
        status=EmbeddingJobStatus.pending.value,
    )
    db.add(job)
    db.flush()
    logger.info("queued %s job %s (source %s)", job_type.value, job.id, rag_source_id)
    return job


def open_job(db: Session, rag_source_id: uuid.UUID) -> EmbeddingJob | None:
    """A pending/processing job for the source, if any."""
    return db.scalar(
        select(EmbeddingJob)
        .where(
            EmbeddingJob.rag_source_id == rag_source_id,
            EmbeddingJob.status.in_(_OPEN_JOB_STATUSES),
        )
        .order_by(EmbeddingJob.created_at.desc())
        .limit(1)
    )


def job_type_for(source: RagSource) -> EmbeddingJobType:
    if source.source_type == RagSourceType.link.value:
        return EmbeddingJobType.crawl
    return EmbeddingJobType.ingest


def _new_source(db: Session, source_id: uuid.UUID, **fields) -> RagSource:
    model = current_embedding_model(db)
    source = RagSource(
        id=source_id,
        status=RagSourceStatus.pending.value,
        chroma_doc_id=str(source_id),
        embedding_model=model,
        collection=collection_for(model),
        **fields,
    )
    db.add(source)
    db.flush()
    return source


# --------------------------------------------------------------------------- #
# Creation
# --------------------------------------------------------------------------- #


def create_document_source(
    db: Session, *, name: str | None, filename: str, content: bytes, content_type: str | None
) -> tuple[RagSource, EmbeddingJob]:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise RagServiceError(f"Unsupported file type {suffix or '(none)'!r}; allowed: {allowed}")
    if not content:
        raise RagServiceError("The file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise RagServiceError(f"File too large: max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

    source_id = uuid.uuid4()
    relative = f"rag/{source_id}/{safe_filename(filename, fallback=f'document{suffix}')}"
    destination = upload_root() / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)

    try:
        source = _new_source(
            db,
            source_id,
            name=(name or "").strip() or filename,
            source_type=RagSourceType.document.value,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            storage_path=relative,
        )
        job = enqueue_job(db, EmbeddingJobType.ingest, rag_source_id=source.id)
        db.commit()
    except Exception:
        db.rollback()
        _remove_source_files(source_id)
        raise
    return source, job


def create_link_source(
    db: Session,
    *,
    name: str | None,
    url: str,
    max_depth: int | None = None,
    max_pages: int | None = None,
    allowed_domains: list[str] | None = None,
) -> tuple[RagSource, EmbeddingJob]:
    """The URL's shape is checked now; the address policy (no private/loopback
    hosts) is enforced at fetch time, on every redirect hop, because DNS can
    change between now and then."""
    url = url.strip()
    try:
        assert_scheme_and_host(url)
    except UnsafeURLError as exc:
        raise RagServiceError(str(exc)) from exc

    depth = DEFAULT_MAX_DEPTH if max_depth is None else max_depth
    pages = DEFAULT_MAX_PAGES if max_pages is None else max_pages
    source = _new_source(
        db,
        uuid.uuid4(),
        name=(name or "").strip() or url,
        source_type=RagSourceType.link.value,
        source_url=url,
        config={
            "max_depth": max(0, min(int(depth), MAX_DEPTH_CAP)),
            "max_pages": max(1, min(int(pages), MAX_PAGES_CAP)),
            "allowed_domains": sorted(
                {d.strip().lower() for d in (allowed_domains or []) if d.strip()}
            ),
        },
    )
    job = enqueue_job(db, EmbeddingJobType.crawl, rag_source_id=source.id)
    db.commit()
    return source, job


def create_text_source(db: Session, *, name: str, text: str) -> tuple[RagSource, EmbeddingJob]:
    if not text.strip():
        raise RagServiceError("The text is empty")
    body = text.strip()
    source = _new_source(
        db,
        uuid.uuid4(),
        name=name.strip() or "Text",
        source_type=RagSourceType.text.value,
        content=body,
        size_bytes=len(body.encode("utf-8")),
    )
    job = enqueue_job(db, EmbeddingJobType.ingest, rag_source_id=source.id)
    db.commit()
    return source, job


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #


def list_sources(
    db: Session,
    *,
    source_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[RagSource], int]:
    filters = []
    if source_type:
        filters.append(RagSource.source_type == source_type)
    if status:
        filters.append(RagSource.status == status)
    total = db.scalar(select(func.count()).select_from(RagSource).where(*filters)) or 0
    rows = db.scalars(
        select(RagSource)
        .where(*filters)
        .order_by(RagSource.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def latest_jobs(db: Session, source_ids: list[uuid.UUID]) -> dict[uuid.UUID, EmbeddingJob]:
    """The newest job per source."""
    if not source_ids:
        return {}
    rows = db.scalars(
        select(EmbeddingJob)
        .where(EmbeddingJob.rag_source_id.in_(source_ids))
        .order_by(EmbeddingJob.rag_source_id, EmbeddingJob.created_at.desc())
        .distinct(EmbeddingJob.rag_source_id)
    ).all()
    return {job.rag_source_id: job for job in rows}


def get_source(db: Session, source_id: uuid.UUID, *, with_pages: bool = False) -> RagSource:
    stmt = select(RagSource).where(RagSource.id == source_id)
    if with_pages:
        stmt = stmt.options(selectinload(RagSource.pages))
    source = db.scalar(stmt)
    if source is None:
        raise NotFoundError("Knowledge-base source not found")
    return source


def list_jobs(
    db: Session,
    *,
    rag_source_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[EmbeddingJob]:
    stmt = select(EmbeddingJob)
    if rag_source_id:
        stmt = stmt.where(EmbeddingJob.rag_source_id == rag_source_id)
    if status:
        stmt = stmt.where(EmbeddingJob.status == status)
    return list(db.scalars(stmt.order_by(EmbeddingJob.created_at.desc()).limit(limit)).all())


def searchable_source_ids(db: Session, scope: list[str] | None = None) -> list[str]:
    """Sources retrieval may use: ready/stale ones, limited to `scope` when
    the config selects some (empty/None = all)."""
    stmt = select(RagSource.id).where(RagSource.status.in_(SEARCHABLE_STATUSES))
    if scope:
        stmt = stmt.where(RagSource.id.in_([uuid.UUID(value) for value in scope]))
    return [str(value) for value in db.scalars(stmt).all()]


def status_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(RagSource.status, func.count()).group_by(RagSource.status)).all()
    counts = {status.value: 0 for status in RagSourceStatus}
    counts.update({status: count for status, count in rows})
    return counts


def total_chunks(db: Session) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(RagSource.chunk_count), 0)).where(
            RagSource.status.in_(SEARCHABLE_STATUSES)
        )
    ) or 0


def job_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(EmbeddingJob.status, func.count()).group_by(EmbeddingJob.status)).all()
    counts = {status.value: 0 for status in EmbeddingJobStatus}
    counts.update({status: count for status, count in rows})
    return counts


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #


def reindex_source(db: Session, source_id: uuid.UUID) -> tuple[RagSource, EmbeddingJob]:
    """Re-embeds a source with the current model and chunk settings. Reuses a
    job that's still waiting rather than queueing a second one."""
    source = get_source(db, source_id)
    job = open_job(db, source.id)
    if job is not None and job.status == EmbeddingJobStatus.processing.value:
        raise ConflictError("This source is being processed right now; try again shortly")
    source.status = RagSourceStatus.pending.value
    source.error = None
    if job is None:
        # Ahead of first-time ingestion: something served now is out of date.
        job = enqueue_job(db, EmbeddingJobType.reindex, rag_source_id=source.id, priority=-1)
    db.commit()
    return source, job


def reindex_all(db: Session) -> int:
    """Queues a reindex for every non-disabled source without an open job."""
    sources = db.scalars(
        select(RagSource).where(RagSource.status != RagSourceStatus.disabled.value)
    ).all()
    queued = 0
    for source in sources:
        if open_job(db, source.id) is not None:
            continue
        source.status = RagSourceStatus.pending.value
        source.error = None
        enqueue_job(db, EmbeddingJobType.reindex, rag_source_id=source.id, priority=-1)
        queued += 1
    db.commit()
    return queued


def retry_job(db: Session, job_id: uuid.UUID) -> EmbeddingJob:
    job = db.get(EmbeddingJob, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    if job.status == EmbeddingJobStatus.processing.value:
        raise ConflictError("The job is running right now")
    if job.status == EmbeddingJobStatus.pending.value:
        return job
    job.status = EmbeddingJobStatus.pending.value
    job.error = None
    job.started_at = None
    job.finished_at = None
    if job.rag_source_id is not None:
        source = db.get(RagSource, job.rag_source_id)
        if source is not None:
            source.status = RagSourceStatus.pending.value
            source.error = None
    if job.job_type == EmbeddingJobType.migrate_embedding.value:
        row = agent_config_repo.get_or_create(db)
        if row.embedding_migration_status == "running":
            raise ConflictError("An embedding migration is already running")
        row.embedding_migration_status = "running"
        row.embedding_migration_target = job.payload.get("target")
        row.embedding_migration_error = None
    db.commit()
    db.refresh(job)
    return job


def delete_source(db: Session, source_id: uuid.UUID) -> int:
    """Removes the source's vectors (from every collection), its stored file
    and its rows. A vector store that refuses to delete doesn't strand the
    row: the failure is logged and the delete goes ahead."""
    source = get_source(db, source_id)
    try:
        removed = rag_index.delete_where({RAG_SOURCE_ID_KEY: str(source.id)})
    except Exception:
        logger.exception("could not purge vectors for source %s; deleting the row anyway", source.id)
        removed = 0
    db.delete(source)  # cascades to pages, jobs and the agent config's scope
    db.commit()
    _remove_source_files(source_id)
    logger.info("deleted rag source %s (%d chunk(s))", source_id, removed)
    return removed


def start_embedding_migration(db: Session, target: str) -> EmbeddingJob | None:
    """Re-embeds every source with `target`, then switches the config to it
    (app.rag.jobs handles migrate_embedding). With nothing to re-embed, the
    switch happens at once and None is returned."""
    row = agent_config_repo.get_or_create(db)
    if row.embedding_migration_status == "running":
        raise ConflictError("An embedding migration is already running")
    if target == row.embedding_model:
        raise RagServiceError("The knowledge base already uses that embedding model")

    has_sources = db.scalar(
        select(func.count())
        .select_from(RagSource)
        .where(RagSource.status != RagSourceStatus.disabled.value)
    )
    if not has_sources:
        row.embedding_model = target
        row.embedding_migration_status = "succeeded"
        row.embedding_migration_target = None
        row.embedding_migration_error = None
        db.commit()
        return None

    row.embedding_migration_status = "running"
    row.embedding_migration_target = target
    row.embedding_migration_error = None
    job = enqueue_job(db, EmbeddingJobType.migrate_embedding, payload={"target": target})
    db.commit()
    return job
