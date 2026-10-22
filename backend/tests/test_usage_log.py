import logging
from types import SimpleNamespace

from livekit.agents.metrics.usage import LLMModelUsage, STTModelUsage, TTSModelUsage

from app.agent.usage_log import UsageLogger


def _usage(*items):
    return SimpleNamespace(usage=SimpleNamespace(model_usage=list(items)))


def _llm(inp, out, cached=0):
    return LLMModelUsage(
        provider="google", model="gemini-3.1-flash-lite",
        input_tokens=inp, input_cached_tokens=cached, output_tokens=out,
    )


def test_each_update_logs_the_increase_and_the_session_total(caplog):
    log = UsageLogger("room-1")
    with caplog.at_level(logging.INFO, logger="agent.usage"):
        log._on_usage(_usage(_llm(1000, 40)))
        log._on_usage(_usage(_llm(2500, 90, cached=800)))
    first, second = caplog.messages
    assert first == (
        "[room-1] LLM google/gemini-3.1-flash-lite: 1000 input tokens, 40 output tokens"
        " | session total: 1000 input tokens, 40 output tokens"
    )
    assert "1500 input tokens (800 cached), 50 output tokens" in second
    assert "session total: 2500 input tokens (800 cached), 90 output tokens" in second


def test_unchanged_models_are_not_logged_again(caplog):
    log = UsageLogger()
    stt = STTModelUsage(provider="elevenlabs", model="scribe_v2_realtime", audio_duration=3.25)
    tts = TTSModelUsage(provider="elevenlabs", model="eleven_v4_turbo", characters_count=120,
                        audio_duration=4.0)
    with caplog.at_level(logging.INFO, logger="agent.usage"):
        log._on_usage(_usage(stt, tts))
        log._on_usage(_usage(stt, tts))
    assert len(caplog.messages) == 2
    assert "STT elevenlabs/scribe_v2_realtime: 3.2s audio" in caplog.messages[0]
    assert "TTS elevenlabs/eleven_v4_turbo: 120 chars, 4.0s audio" in caplog.messages[1]


def test_tool_calls_are_logged_with_arguments(caplog):
    call = SimpleNamespace(name="search_apartments", arguments='{"area": "উত্তরা", "bedrooms": 2}')
    with caplog.at_level(logging.INFO, logger="agent.usage"):
        UsageLogger()._on_tools(SimpleNamespace(function_calls=[call]))
    assert caplog.messages == ['tool search_apartments({"area": "উত্তরা", "bedrooms": 2})']


def test_close_logs_totals_per_model(caplog):
    log = UsageLogger()
    log._on_usage(_usage(_llm(1000, 40)))
    with caplog.at_level(logging.INFO, logger="agent.usage"):
        log._on_close(None)
    assert caplog.messages[0] == "session usage totals:"
    assert "LLM google/gemini-3.1-flash-lite: 1000 input tokens, 40 output tokens" in caplog.messages[1]
