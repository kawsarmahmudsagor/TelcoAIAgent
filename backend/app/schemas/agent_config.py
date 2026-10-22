import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LlmProviderLiteral = Literal["openrouter", "gemini"]
SttTtsProviderLiteral = Literal["elevenlabs", "openrouter", "deepgram"]
ReasoningEffortLiteral = Literal["none", "minimal", "low", "medium", "high"]


class AgentConfigOut(BaseModel):
    """Effective values (saved value, else the env/code default) plus flags
    saying which ones are still on their default."""

    assistant_name: str
    operator_name: str
    operator_phone: str
    operator_address: str
    # Template text; *_is_default = nothing saved, the code default is shown.
    prompt_identity_rules: str
    prompt_is_default: bool
    greeting_inbound: str
    greeting_inbound_is_default: bool
    greeting_nudge: str
    greeting_nudge_is_default: bool

    llm_provider: LlmProviderLiteral
    llm_model: str
    temperature: float | None
    max_output_tokens: int | None
    # The saved value; null = the server default (reasoning_effort_default).
    reasoning_effort: ReasoningEffortLiteral | None
    reasoning_effort_default: ReasoningEffortLiteral
    # The key itself is never returned.
    has_api_key: bool
    # False when SETTINGS_ENCRYPTION_KEY is unset -> saving a key returns 400.
    encryption_available: bool

    stt_tts_provider: SttTtsProviderLiteral
    deepgram_tts_model: str
    elevenlabs_voice_id: str
    # In stt_tts_provider's id format; unused with deepgram.
    elevenlabs_tts_model: str

    # Quick replies (voice, gated calls): the master switch and its two parts.
    quick_reply_enabled: bool
    quick_fast_answer: bool
    quick_filler: bool
    # The saved model; null = the server default (quick_reply_model_default).
    quick_reply_model: str | None
    quick_reply_model_default: str

    rag_enabled: bool
    rag_top_k: int
    rag_similarity_threshold: float
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    embedding_migration_status: str | None
    embedding_migration_target: str | None
    embedding_migration_error: str | None
    # Sources the agent may search; empty = all ready sources.
    rag_source_ids: list[uuid.UUID]
    # False = no OpenRouter key for embeddings (OPENROUTER_API_KEY, or a saved
    # key with OpenRouter as the LLM provider): the knowledge base can't work.
    embedding_ready: bool

    updated_at: datetime | None


class AgentConfigUpdate(BaseModel):
    """Only the fields sent are changed. null resets a field to its default.
    api_key is write-only: omitted/null keeps the saved key, "" clears it."""

    assistant_name: str | None = Field(default=None, max_length=100)
    operator_name: str | None = Field(default=None, max_length=255)
    operator_phone: str | None = Field(default=None, max_length=50)
    operator_address: str | None = Field(default=None, max_length=255)
    prompt_identity_rules: str | None = Field(default=None, max_length=20000)
    greeting_inbound: str | None = Field(default=None, max_length=2000)
    greeting_nudge: str | None = Field(default=None, max_length=2000)

    llm_provider: LlmProviderLiteral | None = None
    llm_model: str | None = Field(default=None, max_length=255)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=32768)
    # OpenRouter only; reset to the default when llm_provider changes.
    reasoning_effort: ReasoningEffortLiteral | None = None
    api_key: str | None = Field(default=None, max_length=500)

    stt_tts_provider: SttTtsProviderLiteral | None = None
    deepgram_tts_model: str | None = Field(default=None, max_length=100)
    elevenlabs_voice_id: str | None = Field(default=None, max_length=100)
    # Reset to the default when stt_tts_provider changes, unless sent with it.
    elevenlabs_tts_model: str | None = Field(default=None, max_length=100)

    quick_reply_enabled: bool | None = None
    quick_fast_answer: bool | None = None
    quick_filler: bool | None = None
    # One of the quick_reply_models options; null = the server default.
    quick_reply_model: str | None = Field(default=None, max_length=255)

    rag_enabled: bool | None = None
    rag_top_k: int | None = Field(default=None, ge=1, le=20)
    rag_similarity_threshold: float | None = Field(default=None, ge=0, le=1)
    chunk_size: int | None = Field(default=None, ge=64, le=4096)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1024)
    # Replaces the source scope; [] = all sources.
    rag_source_ids: list[uuid.UUID] | None = None


class ModelOption(BaseModel):
    id: str
    label: str


class AgentConfigOptions(BaseModel):
    """Suggestions for the dashboard pickers. LLM model ids are free text --
    any OpenRouter/Gemini model id is accepted."""

    llm_providers: list[LlmProviderLiteral]
    llm_models: dict[str, list[ModelOption]]
    embedding_models: list[ModelOption]
    stt_tts_providers: list[SttTtsProviderLiteral]
    deepgram_tts_voices: list[ModelOption]
    elevenlabs_voices: list[ModelOption]
    # Keyed by provider ("elevenlabs", "openrouter"): the ids differ between them.
    elevenlabs_tts_models: dict[str, list[ModelOption]]
    # The only models quick replies accept.
    quick_reply_models: list[ModelOption]
    # Allowed {placeholders} per template field.
    placeholders: dict[str, list[str]]


class VoicePreviewRequest(BaseModel):
    """The unsaved voice choice to audition. `voice` is the ElevenLabs voice id,
    or the Deepgram Aura model. `model` empty = the provider's default."""

    stt_tts_provider: SttTtsProviderLiteral
    voice: str = Field(max_length=100)
    model: str | None = Field(default=None, max_length=100)
    language: Literal["en", "bn"] = "en"
