"""Resolves the agent_config row into the values a call actually uses.

NULL fields fall back to the env Settings (identity, LLM, voice) or the code
defaults in app.agent.prompt_defaults (prompt, greetings), so a fresh database
behaves exactly like the env-only setup did."""

import logging
import string
from dataclasses import dataclass, field

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.agent.prompt_defaults import DEFAULTS, PLACEHOLDERS
from app.agent.quick_models import QUICK_REPLY_MODELS
from app.config import Settings, get_settings
from app.models.agent_config import DEFAULT_EMBEDDING_MODEL, AgentConfig
from app.models.rag import RagSource, RagSourceStatus
from app.services.secrets import decrypt_secret

logger = logging.getLogger("agent_config")

LLM_PROVIDERS = ("openrouter", "gemini")
STT_TTS_PROVIDERS = ("elevenlabs", "openrouter", "deepgram")


class TemplateError(ValueError):
    """A prompt/greeting template uses a placeholder it isn't allowed to."""


def validate_template(template: str, allowed: frozenset[str]) -> None:
    """Rejects anything but plain {name} placeholders from `allowed`: dotted or
    indexed fields, !r/!s conversions, format specs, positional {} and stray
    single braces. Raises TemplateError naming the problem."""
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise TemplateError(f"{exc}. Literal braces must be doubled: {{{{ and }}}}") from exc

    for _literal, field, format_spec, conversion in parsed:
        if field is None:
            continue
        if field == "" or field.isdigit():
            raise TemplateError(
                "Empty or positional placeholder {} isn't allowed. Literal braces must be "
                "doubled: {{ and }}"
            )
        if "." in field or "[" in field:
            raise TemplateError(f"Placeholder {{{field}}} can't use attribute or index access")
        if conversion:
            raise TemplateError(f"Placeholder {{{field}!{conversion}}} can't use a conversion")
        if format_spec:
            raise TemplateError(f"Placeholder {{{field}:{format_spec}}} can't use a format spec")
        if field not in allowed:
            names = ", ".join(f"{{{name}}}" for name in sorted(allowed))
            raise TemplateError(f"Unknown placeholder {{{field}}}. Allowed: {names}")


def render_template(field: str, template: str | None, values: dict[str, str]) -> str:
    """Formats a stored template, falling back to the code default (and logging
    an error) when the stored text is invalid -- a bad row must never break a call."""
    default = DEFAULTS[field]
    if template is not None:
        try:
            validate_template(template, PLACEHOLDERS[field])
            return template.format(**values)
        except (TemplateError, KeyError, ValueError, IndexError):
            logger.error("stored %s template is invalid, using the default", field, exc_info=True)
    return default.format(**values)


@dataclass
class ResolvedAgentConfig:
    assistant_name: str
    operator_name: str
    # Raw templates (None = code default); render with render_template.
    prompt_identity_rules: str | None
    greeting_inbound: str | None
    greeting_nudge: str | None
    llm_provider: str
    llm_model: str
    temperature: float | None
    max_output_tokens: int | None
    # Decrypted dashboard key, else the provider's env key.
    api_key: str
    stt_tts_provider: str
    deepgram_tts_model: str
    elevenlabs_voice_id: str
    # In stt_tts_provider's format; unused with deepgram.
    elevenlabs_tts_model: str = ""
    # Voice provider "elevenlabs" only: the Scribe model ("" = ELEVENLABS_STT_MODEL)
    # and the spoken language, "auto" to detect it per turn.
    elevenlabs_stt_model: str = ""
    elevenlabs_stt_language: str = "auto"
    rag_enabled: bool = False
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.45
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    chunk_size: int = 512
    chunk_overlap: int = 50
    # Sources the agent may search; empty = every searchable source.
    rag_source_ids: list[str] = field(default_factory=list)
    # OpenRouter reasoning effort (none/minimal/low/medium/high).
    reasoning_effort: str = "minimal"
    operator_phone: str = ""
    operator_address: str = ""
    # Voice replies for logged-in browser customers (app.agent.voice_mode).
    voice_replies_enabled: bool = True
    # Quick replies (app.agent.quick_reply): off unless the dashboard turns them on.
    quick_reply_enabled: bool = False
    quick_fast_answer: bool = True
    quick_filler: bool = True
    quick_reply_model: str = ""


def default_model(provider: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return settings.openrouter_model if provider == "openrouter" else settings.gemini_model


def default_stt_tts_provider(settings: Settings | None = None) -> str:
    """The env choice: STT_TTS_PROVIDER, with ELEVENLABS_PROVIDER=openrouter
    turning "elevenlabs" into the OpenRouter-served models."""
    settings = settings or get_settings()
    if settings.stt_tts_provider == "elevenlabs" and settings.elevenlabs_provider == "openrouter":
        return "openrouter"
    return settings.stt_tts_provider


def default_elevenlabs_tts_model(provider: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if provider == "openrouter":
        return settings.elevenlabs_openrouter_tts_model
    return settings.elevenlabs_tts_model


def env_api_key(provider: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return settings.openrouter_api_key if provider == "openrouter" else settings.google_api_key


def resolve(row: AgentConfig | None, settings: Settings | None = None) -> ResolvedAgentConfig:
    settings = settings or get_settings()
    if row is None:
        row = AgentConfig()

    provider = row.llm_provider if row.llm_provider in LLM_PROVIDERS else settings.llm_provider
    api_key = env_api_key(provider, settings)
    if row.api_key_encrypted:
        decrypted = decrypt_secret(row.api_key_encrypted)
        if decrypted:
            api_key = decrypted
        else:
            logger.warning(
                "could not decrypt the saved LLM API key (SETTINGS_ENCRYPTION_KEY unset or "
                "changed?), falling back to the env key"
            )

    stt_tts = (
        row.stt_tts_provider.value
        if row.stt_tts_provider
        else default_stt_tts_provider(settings)
    )

    return ResolvedAgentConfig(
        assistant_name=row.assistant_name or settings.agent_display_name,
        operator_name=row.operator_name or settings.operator_name,
        prompt_identity_rules=row.prompt_identity_rules,
        greeting_inbound=row.greeting_inbound,
        greeting_nudge=row.greeting_nudge,
        llm_provider=provider,
        llm_model=row.llm_model or default_model(provider, settings),
        temperature=row.temperature,
        max_output_tokens=row.max_output_tokens,
        api_key=api_key,
        stt_tts_provider=stt_tts,
        deepgram_tts_model=row.deepgram_tts_model or settings.deepgram_tts_model,
        elevenlabs_voice_id=row.elevenlabs_voice_id or settings.elevenlabs_tts_voice_id,
        elevenlabs_tts_model=(
            row.elevenlabs_tts_model or default_elevenlabs_tts_model(stt_tts, settings)
        ),
        elevenlabs_stt_model=row.elevenlabs_stt_model or settings.elevenlabs_stt_model,
        elevenlabs_stt_language=row.elevenlabs_stt_language or "auto",
        rag_enabled=bool(row.rag_enabled),
        rag_top_k=row.rag_top_k if row.rag_top_k is not None else 5,
        rag_similarity_threshold=(
            row.rag_similarity_threshold if row.rag_similarity_threshold is not None else 0.45
        ),
        embedding_model=row.embedding_model or DEFAULT_EMBEDDING_MODEL,
        chunk_size=row.chunk_size if row.chunk_size is not None else 512,
        chunk_overlap=row.chunk_overlap if row.chunk_overlap is not None else 50,
        rag_source_ids=[str(source.id) for source in (row.rag_sources or [])],
        reasoning_effort=row.reasoning_effort or settings.llm_reasoning_effort,
        operator_phone=row.operator_phone or settings.operator_phone,
        operator_address=row.operator_address or settings.operator_address,
        voice_replies_enabled=row.voice_replies_enabled is not False,
        quick_reply_enabled=bool(row.quick_reply_enabled),
        quick_fast_answer=row.quick_fast_answer is not False,
        quick_filler=row.quick_filler is not False,
        # A saved model dropped from the list since falls back to the default.
        quick_reply_model=(
            row.quick_reply_model
            if row.quick_reply_model in QUICK_REPLY_MODELS
            else settings.quick_reply_model
        ),
    )


def embedding_api_key(config: ResolvedAgentConfig, settings: Settings | None = None) -> str:
    """The OpenRouter key embeddings use: the dashboard-saved key when the LLM
    provider is OpenRouter (resolve() already falls back to the env key there),
    otherwise OPENROUTER_API_KEY. Empty = embeddings can't run."""
    settings = settings or get_settings()
    if config.llm_provider == "openrouter" and config.api_key:
        return config.api_key
    return settings.openrouter_api_key


def chunking_changed(row: AgentConfig, values: dict) -> bool:
    """True if a PATCH's values change chunk_size or chunk_overlap."""
    return any(
        key in values and values[key] != getattr(row, key)
        for key in ("chunk_size", "chunk_overlap")
    )


def mark_sources_stale(db: Session) -> int:
    """Chunk settings changed: every ready source was embedded with the old
    ones. They stay searchable; "Reindex all" re-embeds them. Doesn't commit."""
    result = db.execute(
        update(RagSource)
        .where(RagSource.status == RagSourceStatus.ready.value)
        .values(status=RagSourceStatus.stale.value)
    )
    return result.rowcount or 0


def load() -> ResolvedAgentConfig:
    """Reads the config fresh (call it once per call, so dashboard edits apply to
    the next call without restarting the worker). Falls back to env/code
    defaults if the database can't be read."""
    from app.db.session import SessionLocal
    from app.repositories import agent_config_repo

    db = SessionLocal()
    try:
        return resolve(agent_config_repo.get(db))
    except Exception:
        logger.exception("could not load agent_config, using env defaults")
        return resolve(None)
    finally:
        db.close()
