"""Knowledge-base sources, their crawled pages, the embedding job queue, and
the agent config's source scope (ported from Sellora's rag_source models)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampedBase

_EMPTY_JSONB = text("'{}'::jsonb")


class RagSourceType(str, enum.Enum):
    document = "document"
    link = "link"
    text = "text"


class RagSourceStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    # Embedded with chunk settings that have since changed; still searchable.
    stale = "stale"
    failed = "failed"
    disabled = "disabled"


class RagPageStatus(str, enum.Enum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


class EmbeddingJobType(str, enum.Enum):
    ingest = "ingest"
    crawl = "crawl"
    reindex = "reindex"
    delete = "delete"
    migrate_embedding = "migrate_embedding"


class EmbeddingJobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"


# The agent config's source scope. Empty = every searchable source.
agent_config_rag_sources = Table(
    "agent_config_rag_sources",
    Base.metadata,
    Column(
        "agent_config_id",
        UUID(as_uuid=True),
        ForeignKey("agent_config.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "rag_source_id",
        UUID(as_uuid=True),
        ForeignKey("rag_sources.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class RagSource(TimestampedBase):
    """A knowledge-base source: the Postgres record of a set of Chroma chunks.

    Every chunk carries `rag_source_id` in its metadata, which is what makes
    delete, reindex and per-source retrieval filters possible."""

    __tablename__ = "rag_sources"

    name: Mapped[str] = mapped_column(String(255))
    # RagSourceType / RagSourceStatus values (plain strings, not Postgres enums).
    source_type: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=RagSourceStatus.pending.value, server_default="pending", index=True
    )

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Relative to Settings.upload_path.
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # The text of a `text` source.
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    chroma_doc_id: Mapped[str] = mapped_column(String(128), unique=True)
    # The collection/model the current vectors live in.
    collection: Mapped[str] = mapped_column(String(160))
    embedding_model: Mapped[str] = mapped_column(String(128))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Crawl limits for a link source; last crawl stats.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=_EMPTY_JSONB)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pages: Mapped[list["RagSourcePage"]] = relationship(
        back_populates="rag_source",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RagSourcePage.depth",
    )


class RagSourcePage(TimestampedBase):
    """One crawled page of a `link` source."""

    __tablename__ = "rag_source_pages"
    __table_args__ = (
        UniqueConstraint("rag_source_id", "normalized_url", name="uq_rag_source_page_url"),
    )

    rag_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rag_sources.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), default=RagPageStatus.processing.value)
    chroma_doc_id: Mapped[str] = mapped_column(String(128), index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    rag_source: Mapped[RagSource] = relationship(back_populates="pages")


class EmbeddingJob(TimestampedBase):
    """A unit of work for the scheduler's embedding job runner
    (app.rag.jobs). Claimed with SELECT ... FOR UPDATE SKIP LOCKED."""

    __tablename__ = "embedding_jobs"
    __table_args__ = (
        Index("ix_embedding_jobs_status_priority_created", "status", "priority", "created_at"),
    )

    rag_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rag_sources.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    job_type: Mapped[str] = mapped_column(String(32))
    # Input for jobs not scoped to a source (migrate_embedding: {"target": model}).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=_EMPTY_JSONB)
    status: Mapped[str] = mapped_column(
        String(16), default=EmbeddingJobStatus.pending.value, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Lower runs first: reindex jumps ahead of first-time ingestion.
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=_EMPTY_JSONB)
