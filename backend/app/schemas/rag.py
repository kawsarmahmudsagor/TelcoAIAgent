import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.rag.crawler import MAX_DEPTH_CAP, MAX_PAGES_CAP


class EmbeddingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rag_source_id: uuid.UUID | None
    job_type: str
    status: str
    attempts: int
    payload: dict[str, Any]
    error: str | None
    stats: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RagSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    source_type: str
    status: str
    source_url: str | None
    filename: str | None
    content_type: str | None
    size_bytes: int | None
    embedding_model: str
    chunk_count: int
    config: dict[str, Any]
    error: str | None
    last_indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # The newest job, so the UI can show progress and offer a retry.
    latest_job: EmbeddingJobOut | None = None
    # A seeded KB doc whose file was edited: a reindex embeds the new text.
    file_changed: bool = False


class RagSourcePageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    title: str | None
    depth: int
    status: str
    chunk_count: int
    error: str | None


class RagSourceDetail(RagSourceOut):
    # The text of a text source.
    content: str | None = None
    pages: list[RagSourcePageOut] = []
    jobs: list[EmbeddingJobOut] = []


class RagSourceList(BaseModel):
    items: list[RagSourceOut]
    total: int


class CreateSourceResponse(BaseModel):
    source: RagSourceOut
    job: EmbeddingJobOut


class LinkSourceCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    name: str | None = Field(default=None, max_length=255)
    max_depth: int | None = Field(default=None, ge=0, le=MAX_DEPTH_CAP)
    max_pages: int | None = Field(default=None, ge=1, le=MAX_PAGES_CAP)
    # Empty = the start URL's host (and its subdomains).
    allowed_domains: list[str] = Field(default_factory=list, max_length=20)


class TextSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=200_000)


class ReindexAllResponse(BaseModel):
    queued: int


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    # Defaults: the agent config's top-k / threshold / source scope.
    top_k: int | None = Field(default=None, ge=1, le=20)
    threshold: float | None = Field(default=None, ge=0, le=1)
    source_ids: list[uuid.UUID] | None = None


class RagSearchHit(BaseModel):
    text: str
    score: float | None
    rag_source_id: str | None
    rag_source_name: str | None
    metadata: dict[str, Any]


class RagSearchResponse(BaseModel):
    embedding_model: str
    top_k: int
    threshold: float
    results: list[RagSearchHit]


class MigrateEmbeddingRequest(BaseModel):
    embedding_model: str = Field(min_length=1, max_length=128)


class RagSourceCounts(BaseModel):
    total: int
    pending: int
    processing: int
    ready: int
    stale: int
    failed: int
    disabled: int


class RagStatus(BaseModel):
    rag_enabled: bool
    # False = no OpenRouter key, so nothing can be embedded or searched.
    embedding_ready: bool
    chroma_reachable: bool
    embedding_model: str
    sources: RagSourceCounts
    total_chunks: int
    jobs_pending: int
    jobs_processing: int
    jobs_failed: int
    # Seeded KB docs edited on disk since they were embedded.
    kb_files_changed: int = 0
    embedding_migration_status: str | None
    embedding_migration_target: str | None
    embedding_migration_error: str | None
