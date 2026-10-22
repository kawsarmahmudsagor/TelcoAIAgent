"""The OpenRouter LLM carries the configured reasoning effort."""

from app.agent import entrypoint
from app.config import Settings
from app.services.agent_config_service import ResolvedAgentConfig


def _config(**overrides) -> ResolvedAgentConfig:
    values = dict(
        assistant_name="Alex",
        agency_name="Horizon Realty",
        prompt_identity_rules=None,
        greeting_inbound=None,
        greeting_coldcall=None,
        llm_provider="openrouter",
        llm_model="openai/gpt-6-luna",
        temperature=None,
        max_output_tokens=None,
        api_key="sk-or-test",
        stt_tts_provider="openrouter",
        deepgram_tts_model="aura-2-thalia-en",
        elevenlabs_voice_id="voice",
    )
    values.update(overrides)
    return ResolvedAgentConfig(**values)


def test_openrouter_llm_sends_the_reasoning_effort():
    llm = entrypoint._build_llm(Settings(), _config(reasoning_effort="low"))
    assert llm._opts.extra_body == {"reasoning": {"effort": "low"}}


def test_reasoning_effort_defaults_to_minimal():
    llm = entrypoint._build_llm(Settings(), _config())
    assert llm._opts.extra_body == {"reasoning": {"effort": "minimal"}}
