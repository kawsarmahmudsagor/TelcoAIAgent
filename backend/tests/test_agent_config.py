import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from app.agent.persona import build_system_prompt, knowledge_scope_text
from app.agent.quick_models import QUICK_REPLY_MODELS
from app.agent.prompt_defaults import (
    DEFAULT_GREETING_INBOUND,
    DEFAULT_IDENTITY_AND_RULES,
)
from app.agent.userdata import Channel, SessionUserdata
from app.config import get_settings
from app.db.session import SessionLocal
from app.repositories import agent_config_repo
from app.services import agent_config_service
from app.services.agent_config_service import render_template
from app.services.secrets import decrypt_secret

_COLUMNS = [
    "assistant_name", "operator_name", "operator_phone", "operator_address", "prompt_identity_rules",
    "greeting_inbound", "greeting_nudge", "llm_provider", "llm_model", "temperature", "max_output_tokens",
    "reasoning_effort", "api_key_encrypted", "stt_tts_provider", "deepgram_tts_model", "elevenlabs_voice_id",
    "elevenlabs_tts_model", "rag_enabled", "rag_top_k", "rag_similarity_threshold", "embedding_model", "chunk_size",
    "chunk_overlap", "embedding_migration_status", "embedding_migration_target",
    "embedding_migration_error", "quick_reply_enabled", "quick_fast_answer", "quick_filler",
    "quick_reply_model",
]  # fmt: skip


@pytest.fixture(autouse=True)
def _restore_config_row():
    """Snapshots the singleton row and puts it back after each test."""
    db = SessionLocal()
    try:
        agent_config_repo.get_or_create(db)
        snapshot = db.execute(text(f"select {', '.join(_COLUMNS)} from agent_config")).mappings().one()
        snapshot = dict(snapshot)
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        sets = ", ".join(f"{col} = :{col}" for col in _COLUMNS)
        db.execute(text(f"update agent_config set {sets}"), snapshot)
        db.commit()
    finally:
        db.close()


@pytest.fixture
def encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(get_settings(), "settings_encryption_key", key)
    return key


@pytest.fixture
def no_encryption_key(monkeypatch):
    monkeypatch.setattr(get_settings(), "settings_encryption_key", "")


def _reset_all(api):
    body = {
        field: None
        for field in (
            "assistant_name", "operator_name", "operator_phone", "operator_address",
            "prompt_identity_rules", "greeting_inbound", "greeting_nudge", "llm_provider",
            "llm_model", "temperature",
            "max_output_tokens", "reasoning_effort", "stt_tts_provider", "deepgram_tts_model",
            "elevenlabs_voice_id", "elevenlabs_tts_model", "quick_reply_model",
        )
    }  # fmt: skip
    body["api_key"] = ""
    response = api.patch("/api/agent-config", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _inbound():
    return SessionUserdata(channel=Channel.inbound_chat, room=None)


# --- env fallback ------------------------------------------------------------------


def test_null_config_falls_back_to_env(api):
    settings = get_settings()
    body = _reset_all(api)
    assert body["assistant_name"] == settings.agent_display_name
    assert body["operator_name"] == settings.operator_name
    assert body["llm_provider"] == settings.llm_provider
    expected_model = (
        settings.openrouter_model if settings.llm_provider == "openrouter" else settings.gemini_model
    )
    assert body["llm_model"] == expected_model
    assert body["stt_tts_provider"] == agent_config_service.default_stt_tts_provider()
    assert body["deepgram_tts_model"] == settings.deepgram_tts_model
    assert body["prompt_is_default"] is True
    assert body["prompt_identity_rules"] == DEFAULT_IDENTITY_AND_RULES
    assert body["greeting_inbound"] == DEFAULT_GREETING_INBOUND
    assert body["has_api_key"] is False


def test_patch_sets_and_null_resets(api):
    body = api.patch(
        "/api/agent-config",
        json={"assistant_name": "  Nadia ", "operator_name": "Test Homes", "temperature": 0.4},
    ).json()
    assert body["assistant_name"] == "Nadia"
    assert body["operator_name"] == "Test Homes"
    assert body["temperature"] == 0.4
    # Unsent fields are untouched; null goes back to the env default.
    body = api.patch("/api/agent-config", json={"assistant_name": None}).json()
    assert body["assistant_name"] == get_settings().agent_display_name
    assert body["operator_name"] == "Test Homes"


def test_operator_contact_round_trips_and_blank_resets(api):
    settings = get_settings()
    body = _reset_all(api)
    assert body["operator_phone"] == settings.operator_phone
    assert body["operator_address"] == settings.operator_address
    body = api.patch(
        "/api/agent-config",
        json={"operator_phone": "01900000000", "operator_address": "Road 2, Banani, Dhaka"},
    ).json()
    assert body["operator_phone"] == "01900000000"
    assert body["operator_address"] == "Road 2, Banani, Dhaka"
    resolved = agent_config_service.load()
    assert resolved.operator_phone == "01900000000"
    assert "01900000000" in build_system_prompt(_inbound(), resolved)
    # Blank = back to the env default.
    body = api.patch("/api/agent-config", json={"operator_phone": "  "}).json()
    assert body["operator_phone"] == settings.operator_phone
    assert body["operator_address"] == "Road 2, Banani, Dhaka"


def test_reasoning_effort_null_is_the_server_default(api):
    settings = get_settings()
    body = _reset_all(api)
    assert body["reasoning_effort"] is None
    assert body["reasoning_effort_default"] == settings.llm_reasoning_effort
    assert agent_config_service.load().reasoning_effort == settings.llm_reasoning_effort

    body = api.patch("/api/agent-config", json={"reasoning_effort": "low"}).json()
    assert body["reasoning_effort"] == "low"
    assert agent_config_service.load().reasoning_effort == "low"

    assert api.patch("/api/agent-config", json={"reasoning_effort": "lots"}).status_code == 422


def test_switching_llm_provider_resets_reasoning_effort(api):
    api.patch("/api/agent-config", json={"llm_provider": "openrouter", "reasoning_effort": "low"})
    body = api.patch("/api/agent-config", json={"llm_provider": "gemini"}).json()
    assert body["reasoning_effort"] is None


# --- quick replies -------------------------------------------------------------------


def test_quick_replies_round_trip(api):
    settings = get_settings()
    body = api.patch(
        "/api/agent-config",
        json={"quick_reply_enabled": False, "quick_fast_answer": True, "quick_filler": True,
              "quick_reply_model": None},
    ).json()  # fmt: skip
    assert (body["quick_reply_enabled"], body["quick_fast_answer"], body["quick_filler"]) == (
        False, True, True,
    )  # fmt: skip
    assert body["quick_reply_model"] is None
    assert body["quick_reply_model_default"] == settings.quick_reply_model
    assert agent_config_service.load().quick_reply_model == settings.quick_reply_model

    body = api.patch(
        "/api/agent-config",
        json={"quick_reply_enabled": True, "quick_filler": False,
              "quick_reply_model": "openai/gpt-5.4-nano"},
    ).json()  # fmt: skip
    assert body["quick_reply_enabled"] is True
    assert body["quick_fast_answer"] is True
    assert body["quick_filler"] is False
    assert body["quick_reply_model"] == "openai/gpt-5.4-nano"
    resolved = agent_config_service.load()
    assert resolved.quick_reply_enabled is True
    assert resolved.quick_filler is False
    assert resolved.quick_reply_model == "openai/gpt-5.4-nano"


def test_quick_reply_switches_ignore_null(api):
    api.patch("/api/agent-config", json={"quick_reply_enabled": True})
    body = api.patch("/api/agent-config", json={"quick_reply_enabled": None}).json()
    assert body["quick_reply_enabled"] is True


def test_quick_reply_model_must_be_listed(api):
    response = api.patch("/api/agent-config", json={"quick_reply_model": "openai/gpt-6-luna"})
    assert response.status_code == 422


def test_unlisted_saved_quick_reply_model_falls_back():
    db = SessionLocal()
    try:
        row = agent_config_repo.get_or_create(db)
        agent_config_repo.update(db, row, {"quick_reply_model": "retired/model"})
        resolved = agent_config_service.resolve(agent_config_repo.get(db))
    finally:
        db.close()
    assert resolved.quick_reply_model == get_settings().quick_reply_model


def test_quick_replies_default_off_without_a_row():
    resolved = agent_config_service.resolve(None)
    assert resolved.quick_reply_enabled is False
    assert resolved.quick_fast_answer is True
    assert resolved.quick_filler is True


def test_incoming_call_identity_follows_config():
    db = SessionLocal()
    try:
        row = agent_config_repo.get_or_create(db)
        agent_config_repo.update(db, row, {"assistant_name": None, "operator_name": "Config Realty"})
        resolved = agent_config_service.resolve(agent_config_repo.get(db))
    finally:
        db.close()
    assert resolved.operator_name == "Config Realty"
    assert resolved.assistant_name == get_settings().agent_display_name


def test_chunk_overlap_must_be_below_size(api):
    response = api.patch("/api/agent-config", json={"chunk_size": 100, "chunk_overlap": 100})
    assert response.status_code == 422


# --- secrets -------------------------------------------------------------------------


def test_api_key_round_trip(api, encryption_key):
    response = api.patch("/api/agent-config", json={"api_key": "sk-or-test-123"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["has_api_key"] is True
    assert "sk-or-test-123" not in response.text

    db = SessionLocal()
    try:
        stored = agent_config_repo.get(db).api_key_encrypted
        assert stored and stored != "sk-or-test-123"
        assert decrypt_secret(stored) == "sk-or-test-123"
        assert agent_config_service.resolve(agent_config_repo.get(db)).api_key == "sk-or-test-123"
    finally:
        db.close()

    # Omitted keeps the key; "" clears it.
    assert api.patch("/api/agent-config", json={"temperature": 0.2}).json()["has_api_key"] is True
    assert api.patch("/api/agent-config", json={"api_key": ""}).json()["has_api_key"] is False


def test_undecryptable_key_falls_back_to_env(api, encryption_key, monkeypatch):
    api.patch("/api/agent-config", json={"llm_provider": "openrouter", "api_key": "sk-or-old"})
    # Key rotated -> the saved token can't be read any more.
    monkeypatch.setattr(get_settings(), "settings_encryption_key", Fernet.generate_key().decode())
    db = SessionLocal()
    try:
        resolved = agent_config_service.resolve(agent_config_repo.get(db))
    finally:
        db.close()
    assert resolved.api_key == get_settings().openrouter_api_key


def test_saving_api_key_without_encryption_key_is_400(api, no_encryption_key):
    response = api.patch("/api/agent-config", json={"api_key": "sk-or-test"})
    assert response.status_code == 400
    assert "SETTINGS_ENCRYPTION_KEY" in response.json()["detail"]
    assert api.get("/api/agent-config").json()["encryption_available"] is False


# --- template validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "field, template, problem",
    [
        ("prompt_identity_rules", "You are {name}.", "Unknown placeholder {name}"),
        ("prompt_identity_rules", "You are {agent_name.upper}.", "attribute or index"),
        ("prompt_identity_rules", "You are {agent_name[0]}.", "attribute or index"),
        ("prompt_identity_rules", "You are {agent_name!r}.", "conversion"),
        ("prompt_identity_rules", "You are {agent_name:>10}.", "format spec"),
        ("prompt_identity_rules", "Hello {}.", "positional"),
        ("prompt_identity_rules", "A JSON example: {", "Literal braces must be doubled"),
        ("greeting_inbound", "Greet {client_name}.", "Unknown placeholder {client_name}"),
        ("greeting_nudge", "Greet {current_date}.", "Unknown placeholder {current_date}"),
    ],
)
def test_invalid_templates_are_422(api, field, template, problem):
    response = api.patch("/api/agent-config", json={field: template})
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail.startswith(f"{field}:")
    assert problem in detail


def test_valid_templates_are_saved(api):
    body = api.patch(
        "/api/agent-config",
        json={
            "prompt_identity_rules": "You are {agent_name} of {operator_name}. Use {{braces}}.",
            "greeting_nudge": "Say hi to {customer_name} from {operator_name}: {nudge_text}.",
        },
    ).json()
    assert body["prompt_is_default"] is False
    assert body["greeting_nudge_is_default"] is False
    assert body["greeting_inbound_is_default"] is True


def test_nudge_greeting_defaults_until_saved(api):
    body = _reset_all(api)
    assert body["greeting_nudge_is_default"] is True
    assert "{nudge_text}" in body["greeting_nudge"]


def test_reset_prompt_and_default_text_store_null(api):
    api.patch("/api/agent-config", json={"prompt_identity_rules": "You are {agent_name}."})
    body = api.post("/api/agent-config/reset-prompt").json()
    assert body["prompt_is_default"] is True
    # Saving the default text verbatim keeps tracking the default.
    body = api.patch(
        "/api/agent-config", json={"prompt_identity_rules": DEFAULT_IDENTITY_AND_RULES}
    ).json()
    assert body["prompt_is_default"] is True


# --- prompt building -----------------------------------------------------------------


def test_build_system_prompt_without_config_uses_defaults(api):
    _reset_all(api)
    prompt = build_system_prompt(_inbound())
    assert f"You are {get_settings().agent_display_name}" in prompt
    assert knowledge_scope_text(agent_config_service.resolve(None), False) in prompt
    assert "search_knowledge_base" not in prompt


def test_build_system_prompt_with_config():
    config = agent_config_service.resolve(None)
    config.assistant_name = "Nadia"
    config.operator_name = "Test Homes"
    config.prompt_identity_rules = "You are {agent_name} at {operator_name}. Today is {current_date}."
    prompt = build_system_prompt(_inbound(), config)
    assert prompt.startswith("You are Nadia at Test Homes. Today is ")
    # No {knowledge_scope} in the custom prompt -> appended automatically.
    assert knowledge_scope_text(config, False) in prompt
    assert "mobile account questions" in prompt


def test_knowledge_scope_changes_when_rag_tool_available():
    config = agent_config_service.resolve(None)
    config.operator_name = "Test Homes"
    off = build_system_prompt(_inbound(), config)
    on = build_system_prompt(_inbound(), config, rag_tool_available=True)
    assert knowledge_scope_text(config, False) in off
    assert knowledge_scope_text(config, False) not in on
    assert knowledge_scope_text(config, True) in on
    assert "search_knowledge_base" in on
    assert "Test Homes" in on


def test_invalid_stored_template_falls_back_to_default():
    # Bypasses the API's validation, like a row edited by hand.
    db = SessionLocal()
    try:
        row = agent_config_repo.get_or_create(db)
        agent_config_repo.update(
            db, row, {"prompt_identity_rules": "Hi {secret.attr}", "greeting_inbound": "Hi {"}
        )
        config = agent_config_service.resolve(agent_config_repo.get(db))
    finally:
        db.close()
    prompt = build_system_prompt(_inbound(), config)
    assert "Hi {secret" not in prompt
    assert "SCOPE" in prompt
    values = {"agent_name": "A", "operator_name": "B", "customer_name": ""}
    assert render_template("greeting_inbound", config.greeting_inbound, values) == (
        DEFAULT_GREETING_INBOUND.format(**values)
    )


# --- voice + options ---------------------------------------------------------------------


def test_voice_provider_round_trips_through_agent_config(api):
    assert api.patch("/api/agent-config", json={"stt_tts_provider": "deepgram"}).status_code == 200
    assert api.get("/api/agent-config").json()["stt_tts_provider"] == "deepgram"
    api.patch("/api/agent-config", json={"stt_tts_provider": "elevenlabs"})
    assert api.get("/api/agent-config").json()["stt_tts_provider"] == "elevenlabs"


def test_openrouter_voice_provider_round_trips(api):
    body = api.patch("/api/agent-config", json={"stt_tts_provider": "openrouter"}).json()
    assert body["stt_tts_provider"] == "openrouter"
    assert body["elevenlabs_tts_model"] == get_settings().elevenlabs_openrouter_tts_model


def test_switching_voice_provider_resets_the_model(api):
    api.patch(
        "/api/agent-config",
        json={"stt_tts_provider": "elevenlabs", "elevenlabs_tts_model": "eleven_v3"},
    )
    assert api.get("/api/agent-config").json()["elevenlabs_tts_model"] == "eleven_v3"
    # Same provider again keeps it.
    body = api.patch("/api/agent-config", json={"stt_tts_provider": "elevenlabs"}).json()
    assert body["elevenlabs_tts_model"] == "eleven_v3"
    body = api.patch("/api/agent-config", json={"stt_tts_provider": "openrouter"}).json()
    assert body["elevenlabs_tts_model"] == get_settings().elevenlabs_openrouter_tts_model
    # A model sent with the switch is kept.
    body = api.patch(
        "/api/agent-config",
        json={"stt_tts_provider": "elevenlabs", "elevenlabs_tts_model": "eleven_v4"},
    ).json()
    assert body["elevenlabs_tts_model"] == "eleven_v4"


def test_env_elevenlabs_provider_is_the_default(api, monkeypatch):
    _reset_all(api)
    monkeypatch.setattr(get_settings(), "stt_tts_provider", "elevenlabs")
    monkeypatch.setattr(get_settings(), "elevenlabs_provider", "openrouter")
    assert api.get("/api/agent-config").json()["stt_tts_provider"] == "openrouter"
    monkeypatch.setattr(get_settings(), "elevenlabs_provider", "free")
    assert api.get("/api/agent-config").json()["stt_tts_provider"] == "elevenlabs"


def test_resolved_config_carries_the_tts_model(api):
    api.patch(
        "/api/agent-config",
        json={"stt_tts_provider": "openrouter", "elevenlabs_tts_model": "elevenlabs/eleven-v3"},
    )
    db = SessionLocal()
    try:
        config = agent_config_service.resolve(agent_config_repo.get_or_create(db))
    finally:
        db.close()
    assert config.stt_tts_provider == "openrouter"
    assert config.elevenlabs_tts_model == "elevenlabs/eleven-v3"


def test_settings_shim_is_gone(api):
    assert api.get("/api/settings/voice").status_code == 404


def test_options_list_defaults(api):
    body = api.get("/api/agent-config/options").json()
    settings = get_settings()
    assert settings.openrouter_model in {m["id"] for m in body["llm_models"]["openrouter"]}
    assert settings.gemini_model in {m["id"] for m in body["llm_models"]["gemini"]}
    assert {m["id"] for m in body["embedding_models"]} == {
        "google/gemini-embedding-2",
        "openai/text-embedding-3-large",
    }
    assert body["stt_tts_providers"] == ["elevenlabs", "openrouter", "deepgram"]
    assert len(body["elevenlabs_voices"]) >= 21
    assert "eleven_v4_turbo" in {m["id"] for m in body["elevenlabs_tts_models"]["elevenlabs"]}
    assert "elevenlabs/eleven-v4-turbo" in {
        m["id"] for m in body["elevenlabs_tts_models"]["openrouter"]
    }
    assert {"customer_name", "nudge_text"} <= set(body["placeholders"]["greeting_nudge"])
    assert "knowledge_scope" in body["placeholders"]["prompt_identity_rules"]
    assert [m["id"] for m in body["quick_reply_models"]] == list(QUICK_REPLY_MODELS)


# --- auth -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/agent-config"),
        ("patch", "/api/agent-config"),
        ("get", "/api/agent-config/options"),
        ("post", "/api/agent-config/reset-prompt"),
        ("post", "/api/agent-config/voice-preview"),
    ],
)
def test_agent_config_routes_need_auth(anon_api, method, path):
    kwargs = {"json": {}} if method in {"patch", "post"} else {}
    assert getattr(anon_api, method)(path, **kwargs).status_code == 401


def test_greeting_nudge_placeholders_validated(api):
    ok = api.patch("/api/agent-config", json={"greeting_nudge": "Hi {customer_name}: {nudge_text}"})
    assert ok.status_code == 200
    bad = api.patch("/api/agent-config", json={"greeting_nudge": "Hi {client_name}"})
    assert bad.status_code == 422


def test_greeting_inbound_rejects_old_agency_placeholder(api):
    assert api.patch("/api/agent-config", json={"greeting_inbound": "{agency_name}"}).status_code == 422


def test_removed_greetings_not_in_api(api):
    body = api.get("/api/agent-config").json()
    assert "greeting_coldcall" not in body and "greeting_followup" not in body
