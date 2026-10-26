import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, Float, Index, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TimestampedBase

if TYPE_CHECKING:
    from app.models.rag import RagSource


class SttTtsProvider(str, enum.Enum):
    elevenlabs = "elevenlabs"
    # ElevenLabs models served through OpenRouter (app.agent.openrouter_audio).
    openrouter = "openrouter"
    deepgram = "deepgram"


class EmbeddingMigrationStatus(str, enum.Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


DEFAULT_EMBEDDING_MODEL = "google/gemini-embedding-2"


class AgentConfig(TimestampedBase):
    """Dashboard-configurable agent settings the agent worker reads per call.

    Singleton table: the migration inserts the one row and a unique index on a
    constant stops a second one, so the API and the agent worker never race to
    create it. Always go through app.repositories.agent_config_repo.get.

    Nullable fields mean "use the default": the env Settings for identity, LLM
    and voice, and the code defaults (app.agent.prompt_defaults) for the prompt
    and greetings -- so later improvements to a default still reach installs
    that never customised it. See app.services.agent_config_service.resolve.
    """

    __tablename__ = "agent_config"
    # The singleton guard (migration f3c7a2d9e514): a unique index on a constant.
    __table_args__ = (Index("uq_agent_config_singleton", true(), unique=True),)

    # Identity
    assistant_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Where the agent sends customers for details it doesn't have.
    operator_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    operator_address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Prompt templates (str.format placeholders, validated on save)
    prompt_identity_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Instructions passed to generate_reply, not text spoken verbatim.
    greeting_inbound: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Outbound nudge to a subscriber.
    greeting_nudge: Mapped[str | None] = mapped_column(Text, nullable=True)

    # LLM
    llm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # OpenRouter only; NULL = LLM_REASONING_EFFORT.
    reasoning_effort: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Fernet token (app.services.secrets) for llm_provider's API key. Never
    # returned by the API -- only has_api_key.
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Voice. The Postgres type is the one runtime_settings created.
    stt_tts_provider: Mapped[SttTtsProvider | None] = mapped_column(
        Enum(SttTtsProvider, name="stt_tts_provider"), nullable=True
    )
    deepgram_tts_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    elevenlabs_voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Model id in the chosen provider's format (eleven_v4_turbo directly,
    # elevenlabs/eleven-v4-turbo via OpenRouter), so it resets when that changes.
    elevenlabs_tts_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Browser sessions of logged-in customers answer in voice; off, in text
    # (app.agent.voice_mode). Guests always get text.
    voice_replies_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    # Quick replies (app.agent.quick_reply): the master switch and its two parts.
    quick_reply_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    quick_fast_answer: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    quick_filler: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # One of app.agent.quick_models.QUICK_REPLY_MODELS; NULL = QUICK_REPLY_MODEL.
    quick_reply_model: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Knowledge base (RAG)
    rag_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    rag_top_k: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    rag_similarity_threshold: Mapped[float] = mapped_column(
        Float, default=0.45, server_default="0.45"
    )
    embedding_model: Mapped[str] = mapped_column(
        String(128), default=DEFAULT_EMBEDDING_MODEL, server_default=DEFAULT_EMBEDDING_MODEL
    )
    chunk_size: Mapped[int] = mapped_column(Integer, default=512, server_default="512")
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=50, server_default="50")

    # An in-progress/last "change embedding model" run. NULL status = none ran.
    embedding_migration_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    embedding_migration_target: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_migration_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sources the agent may search (agent_config_rag_sources). Empty = all.
    rag_sources: Mapped[list["RagSource"]] = relationship(
        secondary="agent_config_rag_sources", lazy="selectin"
    )
