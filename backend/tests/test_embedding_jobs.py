"""The embedding job queue and handlers, against the live database with an
in-memory Chroma and a fake embedding model (`rag_fakes`)."""

import pytest
from sqlalchemy import select, text, update

from app.agent.tools.search_knowledge_base import NOTHING_FOUND, search_text
from app.db.session import SessionLocal
from app.models.rag import (
    EmbeddingJob,
    EmbeddingJobStatus,
    EmbeddingJobType,
    RagSource,
    RagSourceStatus,
)
from app.rag import jobs as rag_jobs
from app.rag.config import collection_for
from app.repositories import agent_config_repo
from app.services import agent_config_service, rag_service

PREFIX = "pytest-kb-"
# Claimed before any real job that happens to be waiting in the dev database.
FIRST = -1_000_000

_CONFIG_COLUMNS = [
    "rag_enabled", "rag_top_k", "rag_similarity_threshold", "embedding_model", "chunk_size",
    "chunk_overlap", "embedding_migration_status", "embedding_migration_target",
    "embedding_migration_error",
]  # fmt: skip

FAQ = """### What is the service charge for rentals?
Horizon charges one month's rent as a service fee when the lease is signed.

### What are your office hours?
Our Gulshan office is open Saturday to Thursday, 10am to 7pm.
"""


@pytest.fixture(autouse=True)
def _restore():
    db = SessionLocal()
    try:
        agent_config_repo.get_or_create(db)
        snapshot = dict(
            db.execute(text(f"select {', '.join(_CONFIG_COLUMNS)} from agent_config")).mappings().one()
        )
        before_jobs = set(db.scalars(select(EmbeddingJob.id)).all())
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.execute(text("delete from rag_sources where name like :p"), {"p": PREFIX + "%"})
        new_jobs = set(db.scalars(select(EmbeddingJob.id)).all()) - before_jobs
        if new_jobs:
            db.execute(EmbeddingJob.__table__.delete().where(EmbeddingJob.id.in_(new_jobs)))
        assignments = ", ".join(f"{column} = :{column}" for column in _CONFIG_COLUMNS)
        db.execute(text(f"update agent_config set {assignments}"), snapshot)
        db.commit()
    finally:
        db.close()


def _text_source(name: str = "faq", body: str = FAQ) -> tuple:
    db = SessionLocal()
    try:
        source, job = rag_service.create_text_source(db, name=PREFIX + name, text=body)
        db.execute(update(EmbeddingJob).where(EmbeddingJob.id == job.id).values(priority=FIRST))
        db.commit()
        return source.id, job.id
    finally:
        db.close()


def _claim_and_run(expected_job_id) -> str:
    db = SessionLocal()
    try:
        job = rag_jobs.claim_next_job(db)
        assert job is not None and job.id == expected_job_id
    finally:
        db.close()
    return rag_jobs.run_job(expected_job_id)


def _get(model, row_id):
    db = SessionLocal()
    try:
        return db.get(model, row_id)
    finally:
        db.close()


def test_skip_locked_claims_a_job_once(rag_fakes):
    _first_source, first_job = _text_source("lock-1")
    _second_source, second_job = _text_source("lock-2")
    a, b = SessionLocal(), SessionLocal()
    try:
        claimed_a = rag_jobs.claim_next_job(a, commit=False)  # holds the row lock
        claimed_b = rag_jobs.claim_next_job(b, commit=False)
        assert claimed_a is not None and claimed_a.id == first_job
        # b skipped the locked row instead of waiting for it or taking it too.
        assert claimed_b is not None and claimed_b.id != claimed_a.id
        assert claimed_b.id == second_job
    finally:
        a.rollback()
        b.rollback()
        a.close()
        b.close()
    assert _get(EmbeddingJob, first_job).status == EmbeddingJobStatus.pending.value


def test_orphaned_processing_jobs_go_back_to_pending(rag_fakes):
    source_id, job_id = _text_source("orphan")
    db = SessionLocal()
    try:
        db.execute(
            update(EmbeddingJob).where(EmbeddingJob.id == job_id).values(status="processing")
        )
        db.execute(update(RagSource).where(RagSource.id == source_id).values(status="processing"))
        db.commit()
        assert rag_jobs.reset_orphaned_jobs(db) >= 1
    finally:
        db.close()
    assert _get(EmbeddingJob, job_id).status == EmbeddingJobStatus.pending.value
    assert _get(RagSource, source_id).status == RagSourceStatus.pending.value


def test_text_source_becomes_ready_and_searchable(rag_fakes):
    source_id, job_id = _text_source()
    assert _claim_and_run(job_id) == EmbeddingJobStatus.succeeded.value

    job = _get(EmbeddingJob, job_id)
    source = _get(RagSource, source_id)
    assert job.attempts == 1 and job.stats["chunks"] == source.chunk_count == 2
    assert source.status == RagSourceStatus.ready.value and source.last_indexed_at is not None
    assert source.collection == collection_for(source.embedding_model)

    config = agent_config_service.load()
    config.rag_similarity_threshold = 0.0
    config.rag_source_ids = [str(source_id)]
    answer = search_text("what are the office hours", config)
    assert "Saturday to Thursday" in answer and "<untrusted_context" in answer
    assert "head office" in answer

    # Deleting the source removes its vectors and it's no longer searchable.
    db = SessionLocal()
    try:
        rag_service.delete_source(db, source_id)
    finally:
        db.close()
    assert search_text("office hours", config) == NOTHING_FOUND
    assert rag_fakes.get_collection(collection_for(source.embedding_model)).count() == 0


def test_missing_key_fails_fast_with_a_clear_error(rag_fakes, monkeypatch):
    monkeypatch.setattr(rag_jobs, "embedding_key", lambda config: "")
    source_id, job_id = _text_source("nokey")
    assert _claim_and_run(job_id) == EmbeddingJobStatus.failed.value
    job = _get(EmbeddingJob, job_id)
    source = _get(RagSource, source_id)
    assert "OpenRouter API key" in job.error
    assert source.status == RagSourceStatus.failed.value and source.error == job.error

    # A manual retry re-queues it, and it succeeds once a key is there.
    monkeypatch.setattr(rag_jobs, "embedding_key", lambda config: "test-key")
    db = SessionLocal()
    try:
        retried = rag_service.retry_job(db, job_id)
        assert retried.status == EmbeddingJobStatus.pending.value
    finally:
        db.close()
    assert _get(RagSource, source_id).status == RagSourceStatus.pending.value
    assert _claim_and_run(job_id) == EmbeddingJobStatus.succeeded.value
    assert _get(EmbeddingJob, job_id).attempts == 2


def test_chunk_change_marks_ready_sources_stale_and_reindex_all_requeues(rag_fakes, api):
    source_id, job_id = _text_source("stale")
    _claim_and_run(job_id)
    current = api.get("/api/agent-config").json()

    response = api.patch("/api/agent-config", json={"chunk_size": current["chunk_size"] + 64})
    assert response.status_code == 200
    assert _get(RagSource, source_id).status == RagSourceStatus.stale.value

    # Stale sources stay searchable until they're re-embedded.
    db = SessionLocal()
    try:
        assert str(source_id) in rag_service.searchable_source_ids(db)
    finally:
        db.close()

    assert api.post("/api/rag/reindex-all").json()["queued"] >= 1
    assert _get(RagSource, source_id).status == RagSourceStatus.pending.value
    db = SessionLocal()
    try:
        job = rag_service.open_job(db, source_id)
        assert job.job_type == EmbeddingJobType.reindex.value
        db.execute(update(EmbeddingJob).where(EmbeddingJob.id == job.id).values(priority=FIRST))
        db.commit()
        job_id = job.id
    finally:
        db.close()
    assert _claim_and_run(job_id) == EmbeddingJobStatus.succeeded.value
    assert _get(RagSource, source_id).status == RagSourceStatus.ready.value


def test_embedding_migration_reembeds_then_flips_the_model(rag_fakes, api):
    db = SessionLocal()
    try:
        others = db.scalar(
            select(RagSource.id).where(~RagSource.name.like(PREFIX + "%")).limit(1)
        )
    finally:
        db.close()
    if others is not None:
        pytest.skip("the dev database has real knowledge-base sources; not migrating them")

    source_id, job_id = _text_source("migrate")
    _claim_and_run(job_id)
    old_model = _get(RagSource, source_id).embedding_model
    target = next(
        option["id"]
        for option in api.get("/api/agent-config/options").json()["embedding_models"]
        if option["id"] != old_model
    )

    response = api.post("/api/agent-config/migrate-embedding", json={"embedding_model": target})
    assert response.status_code == 202, response.text
    assert response.json()["embedding_migration_status"] == "running"
    assert response.json()["embedding_model"] == old_model  # still serving the old one
    again = api.post("/api/agent-config/migrate-embedding", json={"embedding_model": target})
    assert again.status_code == 409

    db = SessionLocal()
    try:
        migration = db.scalar(
            select(EmbeddingJob).where(
                EmbeddingJob.job_type == EmbeddingJobType.migrate_embedding.value,
                EmbeddingJob.status == EmbeddingJobStatus.pending.value,
            )
        )
        db.execute(update(EmbeddingJob).where(EmbeddingJob.id == migration.id).values(priority=FIRST))
        db.commit()
        migration_id = migration.id
    finally:
        db.close()
    assert _claim_and_run(migration_id) == EmbeddingJobStatus.succeeded.value

    config = api.get("/api/agent-config").json()
    assert config["embedding_model"] == target
    assert config["embedding_migration_status"] == "succeeded"
    source = _get(RagSource, source_id)
    assert source.embedding_model == target and source.collection == collection_for(target)
    names = [entry if isinstance(entry, str) else entry.name for entry in rag_fakes.list_collections()]
    assert collection_for(target) in names and collection_for(old_model) not in names


def test_unknown_migration_target_is_rejected(api):
    response = api.post("/api/agent-config/migrate-embedding", json={"embedding_model": "nope/model"})
    assert response.status_code == 422


def test_property_changes_queue_a_properties_sync(rag_fakes, api):
    db = SessionLocal()
    try:
        before = set(db.scalars(select(EmbeddingJob.id)).all())
        existing = rag_service.properties_source(db)
        source, job = rag_service.sync_properties(db)
        if existing is None:
            source.name = PREFIX + "properties"
            db.commit()
        source_id = source.id
        if job.id not in before:
            # Pretend our sync ran, so the next change has to queue a new one.
            job.status = EmbeddingJobStatus.succeeded.value
            db.commit()
    finally:
        db.close()

    created = api.post(
        "/api/properties",
        json={
            "title": PREFIX + "listing",
            "address_line": "Road 1",
            "city": "Dhaka",
            "neighborhood": "Gulshan",
            "property_type": "apartment",
            "listing_type": "rent",
            "price": 50000,
            "bedrooms": 2,
            "bathrooms": 2,
        },
    )
    assert created.status_code == 201, created.text
    try:
        db = SessionLocal()
        try:
            job = rag_service.open_job(db, source_id)
            assert job is not None and job.job_type == EmbeddingJobType.sync_properties.value
            # A second change while that sync still waits doesn't add another.
            api.delete(f"/api/properties/{created.json()['id']}")
            pending = db.scalars(
                select(EmbeddingJob).where(
                    EmbeddingJob.rag_source_id == source_id, EmbeddingJob.status == "pending"
                )
            ).all()
            assert len(pending) == 1
        finally:
            db.close()
    finally:
        db = SessionLocal()
        try:
            db.execute(text("delete from properties where title = :t"), {"t": PREFIX + "listing"})
            db.commit()
        finally:
            db.close()
