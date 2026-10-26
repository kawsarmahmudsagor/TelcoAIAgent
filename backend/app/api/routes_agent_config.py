from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.prompt_defaults import DEFAULTS, PLACEHOLDERS
from app.agent.quick_models import QUICK_REPLY_LABELS, QUICK_REPLY_MODELS
from app.api.deps import get_current_admin, get_db
from app.config import get_settings
from app.models.agent_config import AgentConfig, SttTtsProvider
from app.models.rag import RagSource
from app.repositories import agent_config_repo
from app.schemas.agent_config import (
    AgentConfigOptions,
    AgentConfigOut,
    AgentConfigUpdate,
    ModelOption,
    VoicePreviewRequest,
)
from app.schemas.rag import MigrateEmbeddingRequest
from app.services import agent_config_service, rag_service, voice_preview
from app.services.agent_config_service import TemplateError, validate_template
from app.services.secrets import EncryptionKeyMissing, encrypt_secret, encryption_available

router = APIRouter(
    prefix="/api/agent-config",
    tags=["agent-config"],
    dependencies=[Depends(get_current_admin)],
)

_TEMPLATE_FIELDS = tuple(PLACEHOLDERS)
# Can't be reset to a default (no NULL); a null in the PATCH body is ignored.
_NOT_NULLABLE = {
    "rag_enabled",
    "rag_top_k",
    "rag_similarity_threshold",
    "chunk_size",
    "chunk_overlap",
    "voice_replies_enabled",
    "quick_reply_enabled",
    "quick_fast_answer",
    "quick_filler",
}

# Suggestions only -- the dashboard also accepts any model id typed in.
_OPENROUTER_MODELS = [
    ("openai/gpt-6-luna", "OpenAI GPT-6 Luna"),
    ("openai/gpt-5.6-luna", "OpenAI GPT-5.6 Luna"),
    ("openai/gpt-5.6-terra", "OpenAI GPT-5.6 Terra"),
    ("openai/gpt-5.4-nano", "OpenAI GPT-5.4 Nano"),
    ("google/gemini-3.5-flash", "Google Gemini 3.5 Flash"),
    ("google/gemini-3.5-flash-lite", "Google Gemini 3.5 Flash Lite"),
    ("google/gemini-3.1-flash-lite", "Google Gemini 3.1 Flash Lite"),
    ("openai/gpt-oss-120b", "OpenAI gpt-oss-120b"),
    ("x-ai/grok-4.7", "xAI Grok 4.7"),
    ("anthropic/claude-haiku-4.5", "Anthropic Claude Haiku 4.5"),
]
_GEMINI_MODELS = [
    ("gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite"),
    ("gemini-3.6-flash", "Gemini 3.6 Flash (low free-tier daily limit)"),
]
_EMBEDDING_MODELS = [
    ("google/gemini-embedding-2", "Google Gemini Embedding 2"),
    ("openai/text-embedding-3-large", "OpenAI text-embedding-3-large"),
]
_DEEPGRAM_VOICES = [
    ("aura-2-thalia-en", "Thalia (female, US)"),
    ("aura-2-andromeda-en", "Andromeda (female, US)"),
    ("aura-2-asteria-en", "Asteria (female, US)"),
    ("aura-2-luna-en", "Luna (female, US)"),
    ("aura-2-aurora-en", "Aurora (female, US)"),
    ("aura-2-hera-en", "Hera (female, US)"),
    ("aura-2-iris-en", "Iris (female, US)"),
    ("aura-2-apollo-en", "Apollo (male, US)"),
    ("aura-2-arcas-en", "Arcas (male, US)"),
    ("aura-2-orion-en", "Orion (male, US)"),
    ("aura-2-atlas-en", "Atlas (male, US)"),
    ("aura-2-zeus-en", "Zeus (male, US)"),
]
# ElevenLabs' premade voices: usable on every account, free tier included, and by
# the same id through OpenRouter. Any other voice id can still be typed in.
_ELEVENLABS_VOICES = [
    ("EXAVITQu4vr4xnSDxMaL", "Sarah (female, US, reassuring)"),
    ("cgSgspJ2msm6clMCkdW9", "Jessica (female, US, playful)"),
    ("hpp4J3VqNfWAUOO0d1Us", "Bella (female, US, warm)"),
    ("XrExE9yKIg1WjnnlVkGX", "Matilda (female, US, professional)"),
    ("FGY2WhTYpPnrIDTdsKH5", "Laura (female, US, upbeat)"),
    ("Xb7hH8MSUJpSbSDYk0k2", "Alice (female, British, clear)"),
    ("pFZP5JQG7iQjIQuC4Bku", "Lily (female, British, velvety)"),
    ("SAz9YHcvj6GT2YYXdXww", "River (neutral, US, relaxed)"),
    ("CwhRBWXzGAHq8TQ4Fs17", "Roger (male, US, laid-back)"),
    ("cjVigY5qzO86Huf0OWal", "Eric (male, US, trustworthy)"),
    ("iP95p4xoKVk53GoZ742B", "Chris (male, US, down-to-earth)"),
    ("bIHbv24MWmeRgasZH58o", "Will (male, US, optimistic)"),
    ("nPczCjzI2devNBz1zQrb", "Brian (male, US, deep)"),
    ("pNInz6obpgDQGcFmaJgB", "Adam (male, US, firm)"),
    ("TX3LPaxmHKxFdv7VOQHJ", "Liam (male, US, energetic)"),
    ("N2lVS1w4EtoT3dr4eOWO", "Callum (male, US, husky)"),
    ("SOYHLrjzK2X1ezoPC6cr", "Harry (male, US, fierce)"),
    ("pqHfZKP75CvOlQylNhV4", "Bill (male, US, mature)"),
    ("JBFqnCBsd6RMkjVDRZzb", "George (male, British, storyteller)"),
    ("onwK4e9ZLuTAKqWW03F9", "Daniel (male, British, broadcaster)"),
    ("IKne3meq5aSn9XLyUdCD", "Charlie (male, Australian, energetic)"),
]
# Only the first four speak Bangla (checked against ElevenLabs' /v1/models).
_ELEVENLABS_TTS_MODELS = [
    ("eleven_v4_turbo", "Eleven v4 Turbo (fast, Bangla)"),
    ("eleven_v4", "Eleven v4 (expressive, Bangla)"),
    ("eleven_v3", "Eleven v3 (expressive, Bangla, slower)"),
    ("eleven_v3_conversational", "Eleven v3 Conversational (Bangla)"),
    ("eleven_flash_v2_5", "Eleven Flash v2.5 (fastest, no Bangla)"),
    ("eleven_turbo_v2_5", "Eleven Turbo v2.5 (no Bangla)"),
    ("eleven_multilingual_v2", "Eleven Multilingual v2 (no Bangla)"),
]
_OPENROUTER_TTS_MODELS = [
    (f"elevenlabs/{model_id.replace('_', '-').replace('v2-5', 'v2.5')}", label)
    for model_id, label in _ELEVENLABS_TTS_MODELS
]


def _options(pairs: list[tuple[str, str]], extra: str | None = None, label: str = "") -> list[ModelOption]:
    """Adds `extra` (an env default) to the front if the curated list lacks it."""
    options = [ModelOption(id=model_id, label=model_label) for model_id, model_label in pairs]
    if extra and all(option.id != extra for option in options):
        options.insert(0, ModelOption(id=extra, label=label or extra))
    return options


def _to_out(row: AgentConfig) -> AgentConfigOut:
    resolved = agent_config_service.resolve(row)
    return AgentConfigOut(
        assistant_name=resolved.assistant_name,
        operator_name=resolved.operator_name,
        operator_phone=resolved.operator_phone,
        operator_address=resolved.operator_address,
        prompt_identity_rules=row.prompt_identity_rules or DEFAULTS["prompt_identity_rules"],
        prompt_is_default=row.prompt_identity_rules is None,
        greeting_inbound=row.greeting_inbound or DEFAULTS["greeting_inbound"],
        greeting_inbound_is_default=row.greeting_inbound is None,
        greeting_nudge=row.greeting_nudge or DEFAULTS["greeting_nudge"],
        greeting_nudge_is_default=row.greeting_nudge is None,
        llm_provider=resolved.llm_provider,
        llm_model=resolved.llm_model,
        temperature=resolved.temperature,
        max_output_tokens=resolved.max_output_tokens,
        reasoning_effort=row.reasoning_effort,
        reasoning_effort_default=get_settings().llm_reasoning_effort,
        has_api_key=bool(row.api_key_encrypted),
        encryption_available=encryption_available(),
        stt_tts_provider=resolved.stt_tts_provider,
        deepgram_tts_model=resolved.deepgram_tts_model,
        elevenlabs_voice_id=resolved.elevenlabs_voice_id,
        elevenlabs_tts_model=resolved.elevenlabs_tts_model,
        voice_replies_enabled=resolved.voice_replies_enabled,
        quick_reply_enabled=resolved.quick_reply_enabled,
        quick_fast_answer=resolved.quick_fast_answer,
        quick_filler=resolved.quick_filler,
        quick_reply_model=(
            row.quick_reply_model if row.quick_reply_model in QUICK_REPLY_MODELS else None
        ),
        quick_reply_model_default=get_settings().quick_reply_model,
        rag_enabled=resolved.rag_enabled,
        rag_top_k=resolved.rag_top_k,
        rag_similarity_threshold=resolved.rag_similarity_threshold,
        embedding_model=resolved.embedding_model,
        chunk_size=resolved.chunk_size,
        chunk_overlap=resolved.chunk_overlap,
        embedding_migration_status=row.embedding_migration_status,
        embedding_migration_target=row.embedding_migration_target,
        embedding_migration_error=row.embedding_migration_error,
        rag_source_ids=[source.id for source in row.rag_sources],
        embedding_ready=bool(agent_config_service.embedding_api_key(resolved)),
        updated_at=row.updated_at,
    )


@router.get("", response_model=AgentConfigOut)
def get_agent_config(db: Session = Depends(get_db)) -> AgentConfigOut:
    return _to_out(agent_config_repo.get_or_create(db))


@router.patch("", response_model=AgentConfigOut)
def update_agent_config(payload: AgentConfigUpdate, db: Session = Depends(get_db)) -> AgentConfigOut:
    row = agent_config_repo.get_or_create(db)
    data = payload.model_dump(exclude_unset=True)
    api_key = data.pop("api_key", None)
    scope_ids = data.pop("rag_source_ids", None)

    values: dict = {}
    for key, value in data.items():
        if key in _NOT_NULLABLE:
            if value is not None:
                values[key] = value
            continue
        if isinstance(value, str) and not value.strip():
            value = None  # blank = back to the default
        if key in _TEMPLATE_FIELDS and value is not None:
            try:
                validate_template(value, PLACEHOLDERS[key])
            except TemplateError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{key}: {exc}") from exc
            if value.strip() == DEFAULTS[key].strip():
                value = None  # identical to the default -> keep tracking the default
        elif isinstance(value, str):
            value = value.strip()
        if key == "stt_tts_provider" and value is not None:
            value = SttTtsProvider(value)
        if key == "quick_reply_model" and value is not None and value not in QUICK_REPLY_MODELS:
            allowed = ", ".join(QUICK_REPLY_MODELS)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"quick_reply_model: unknown model. Allowed: {allowed}",
            )
        values[key] = value

    chunk_size = values.get("chunk_size", row.chunk_size)
    chunk_overlap = values.get("chunk_overlap", row.chunk_overlap)
    if chunk_overlap >= chunk_size:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "chunk_overlap must be smaller than chunk_size"
        )

    if "llm_provider" in values:
        current = agent_config_service.resolve(row).llm_provider
        new = values["llm_provider"] or get_settings().llm_provider
        if new != current:
            # A model id / API key for one provider is meaningless for the other.
            values.setdefault("llm_model", None)
            values.setdefault("reasoning_effort", None)
            if api_key is None:
                values["api_key_encrypted"] = None

    if "stt_tts_provider" in values:
        current = agent_config_service.resolve(row).stt_tts_provider
        new = values["stt_tts_provider"] or agent_config_service.default_stt_tts_provider()
        if new != current:
            # ElevenLabs and OpenRouter name the same models differently.
            values.setdefault("elevenlabs_tts_model", None)

    if api_key is not None:
        if api_key == "":
            values["api_key_encrypted"] = None
        elif not api_key.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "api_key can't be blank")
        else:
            try:
                values["api_key_encrypted"] = encrypt_secret(api_key.strip())
            except EncryptionKeyMissing as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Can't save an API key: SETTINGS_ENCRYPTION_KEY is not configured on the server",
                ) from exc

    if scope_ids is not None:
        wanted = set(scope_ids)
        sources = db.scalars(select(RagSource).where(RagSource.id.in_(wanted))).all() if wanted else []
        missing = wanted - {source.id for source in sources}
        if missing:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Unknown knowledge-base source(s): {', '.join(sorted(map(str, missing)))}",
            )
        row.rag_sources = list(sources)

    if agent_config_service.chunking_changed(row, values):
        # Existing chunks were cut with the old settings; "Reindex all" redoes them.
        agent_config_service.mark_sources_stale(db)

    return _to_out(agent_config_repo.update(db, row, values))


@router.post(
    "/migrate-embedding", response_model=AgentConfigOut, status_code=status.HTTP_202_ACCEPTED
)
def migrate_embedding(payload: MigrateEmbeddingRequest, db: Session = Depends(get_db)) -> AgentConfigOut:
    """Switches the embedding model: every source is re-embedded with the new
    model in the background while the old vectors keep serving, then the
    config flips over. Poll GET /api/agent-config (embedding_migration_status)."""
    target = payload.embedding_model.strip()
    if target not in {model_id for model_id, _label in _EMBEDDING_MODELS}:
        allowed = ", ".join(model_id for model_id, _label in _EMBEDDING_MODELS)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown embedding model. Allowed: {allowed}"
        )
    row = agent_config_repo.get_or_create(db)
    if not agent_config_service.embedding_api_key(agent_config_service.resolve(row)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No OpenRouter API key for embeddings: set OPENROUTER_API_KEY or save an OpenRouter key",
        )
    try:
        rag_service.start_embedding_migration(db, target)
    except rag_service.ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except rag_service.RagServiceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db.refresh(row)
    return _to_out(row)


@router.post("/reset-prompt", response_model=AgentConfigOut)
def reset_prompt(db: Session = Depends(get_db)) -> AgentConfigOut:
    """Back to the code default prompt (stored as NULL, so later improvements
    to the default apply here too)."""
    row = agent_config_repo.get_or_create(db)
    return _to_out(agent_config_repo.update(db, row, {"prompt_identity_rules": None}))


@router.get("/options", response_model=AgentConfigOptions)
def get_options() -> AgentConfigOptions:
    settings = get_settings()
    return AgentConfigOptions(
        llm_providers=["openrouter", "gemini"],
        llm_models={
            "openrouter": _options(_OPENROUTER_MODELS, settings.openrouter_model),
            "gemini": _options(_GEMINI_MODELS, settings.gemini_model),
        },
        embedding_models=_options(_EMBEDDING_MODELS),
        stt_tts_providers=["elevenlabs", "openrouter", "deepgram"],
        deepgram_tts_voices=_options(_DEEPGRAM_VOICES, settings.deepgram_tts_model),
        elevenlabs_voices=_options(
            _ELEVENLABS_VOICES, settings.elevenlabs_tts_voice_id, label="Default voice (from env)"
        ),
        elevenlabs_tts_models={
            "elevenlabs": _options(_ELEVENLABS_TTS_MODELS, settings.elevenlabs_tts_model),
            "openrouter": _options(
                _OPENROUTER_TTS_MODELS, settings.elevenlabs_openrouter_tts_model
            ),
        },
        quick_reply_models=[
            ModelOption(id=model_id, label=QUICK_REPLY_LABELS.get(model_id, model_id))
            for model_id in QUICK_REPLY_MODELS
        ],
        placeholders={field: sorted(names) for field, names in PLACEHOLDERS.items()},
    )


@router.post(
    "/voice-preview",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}}},
)
async def preview_voice(payload: VoicePreviewRequest, db: Session = Depends(get_db)) -> Response:
    """A sample line in `language`, spoken with the given (unsaved) voice choice.
    Uses the provider's real API, so each preview spends credits."""
    config = agent_config_service.resolve(agent_config_repo.get_or_create(db))
    try:
        audio = await voice_preview.synthesize(
            settings=get_settings(),
            config=config,
            provider=payload.stt_tts_provider,
            voice=payload.voice,
            model=payload.model,
            language=payload.language,
        )
    except voice_preview.PreviewError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
