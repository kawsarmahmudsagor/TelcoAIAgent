"""Voice preview: what each provider is sent and how failures read in the dashboard.
Requests go to an httpx.MockTransport, never the network."""

import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.services import voice_preview
from app.services.agent_config_service import ResolvedAgentConfig
from app.services.voice_preview import PreviewError, synthesize

_MP3 = b"ID3fake-mp3"


def _settings(**values) -> Settings:
    base = dict(
        elevenlabs_api_keys="", elevenlabs_api_key="", deepgram_api_key="",
        openrouter_api_key="", elevenlabs_tts_model="eleven_v4_turbo",
        elevenlabs_openrouter_tts_model="elevenlabs/eleven-v4-turbo",
    )  # fmt: skip
    return Settings(_env_file=None, **{**base, **values})


def _config(**values) -> ResolvedAgentConfig:
    base = dict(
        assistant_name="Alexa", agency_name="Horizon Realty", prompt_identity_rules=None,
        greeting_inbound=None, greeting_coldcall=None, llm_provider="gemini", llm_model="m",
        temperature=None, max_output_tokens=None, api_key="", stt_tts_provider="elevenlabs",
        deepgram_tts_model="aura-2-thalia-en", elevenlabs_voice_id="v",
    )  # fmt: skip
    return ResolvedAgentConfig(**{**base, **values})


def _run(handler, settings, *, provider, voice="voice-1", model=None, language="en"):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await synthesize(
                settings=settings, config=_config(), provider=provider,
                voice=voice, model=model, language=language, client=client,
            )  # fmt: skip

    return asyncio.run(go())


def test_elevenlabs_moves_on_from_a_spent_key():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.headers["xi-api-key"] == "k1":
            return httpx.Response(401, json={"detail": {"status": "quota_exceeded"}})
        return httpx.Response(200, content=_MP3)

    audio = _run(
        handler, _settings(elevenlabs_api_keys="k1,k2"), provider="elevenlabs", language="bn"
    )
    assert audio == _MP3
    assert [r.headers["xi-api-key"] for r in seen] == ["k1", "k2"]
    assert seen[1].url.path == "/v1/text-to-speech/voice-1"
    body = json.loads(seen[1].content)
    assert body["model_id"] == "eleven_v4_turbo"
    assert "Horizon Realty" in body["text"]
    assert "আসসালামু" in body["text"]


def test_elevenlabs_bad_voice_stops_at_the_first_key():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(404, json={"detail": {"status": "voice_not_found", "message": "nope"}})

    with pytest.raises(PreviewError) as exc_info:
        _run(handler, _settings(elevenlabs_api_keys="k1,k2"), provider="elevenlabs")
    assert exc_info.value.status_code == 400
    assert "nope" in str(exc_info.value)
    assert len(seen) == 1


def test_elevenlabs_all_keys_spent_is_a_refusal_not_an_outage():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": {"status": "quota_exceeded"}})

    with pytest.raises(PreviewError, match="refused it on every key: quota_exceeded") as exc_info:
        _run(handler, _settings(elevenlabs_api_keys="k1,k2"), provider="elevenlabs")
    assert exc_info.value.status_code == 400


def test_elevenlabs_library_voice_on_free_keys_explains_the_way_out():
    message = "Free users cannot use library voices via the API. Add $5 of credits."

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402, json={"detail": {"status": "payment_required", "message": message}}
        )

    with pytest.raises(PreviewError) as exc_info:
        _run(handler, _settings(elevenlabs_api_keys="k1,k2"), provider="elevenlabs")
    text = str(exc_info.value)
    assert text.count(message) == 1
    assert "ElevenLabs via OpenRouter" in text
    assert exc_info.value.status_code == 400


def test_elevenlabs_mixed_failures_list_each_key():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["xi-api-key"] == "k1":
            return httpx.Response(401, json={"detail": {"status": "quota_exceeded"}})
        return httpx.Response(500, json={"detail": "boom"})

    with pytest.raises(PreviewError, match="Every ElevenLabs key failed") as exc_info:
        _run(handler, _settings(elevenlabs_api_keys="k1,k2"), provider="elevenlabs")
    assert "…" in str(exc_info.value)
    assert exc_info.value.status_code == 503


@pytest.mark.parametrize("provider", ["openrouter", "deepgram"])
def test_upstream_outage_is_503_never_502(provider):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    s = _settings(openrouter_api_key="or", deepgram_api_key="dg")
    with pytest.raises(PreviewError) as exc_info:
        _run(handler, s, provider=provider, voice="aura-2-luna-en")
    assert exc_info.value.status_code == 503


def test_timeout_is_503():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(PreviewError, match="too long") as exc_info:
        _run(handler, _settings(openrouter_api_key="or"), provider="openrouter")
    assert exc_info.value.status_code == 503


def test_openrouter_request():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_MP3)

    audio = _run(
        handler, _settings(openrouter_api_key="or"), provider="openrouter",
        model="elevenlabs/eleven-v3",
    )  # fmt: skip
    assert audio == _MP3
    (request,) = seen
    assert request.url.path == "/api/v1/audio/speech"
    assert request.headers["authorization"] == "Bearer or"
    body = json.loads(request.content)
    assert body["model"] == "elevenlabs/eleven-v3"
    assert body["voice"] == "voice-1"
    assert body["response_format"] == "mp3"


def test_openrouter_defaults_its_own_model():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=_MP3)

    _run(handler, _settings(openrouter_api_key="or"), provider="openrouter")
    assert seen[0]["model"] == "elevenlabs/eleven-v4-turbo"


def test_deepgram_request_and_no_bangla():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_MP3)

    s = _settings(deepgram_api_key="dg")
    assert _run(handler, s, provider="deepgram", voice="aura-2-luna-en") == _MP3
    assert seen[0].url.params["model"] == "aura-2-luna-en"
    assert seen[0].headers["authorization"] == "Token dg"
    with pytest.raises(PreviewError, match="English-only"):
        _run(handler, s, provider="deepgram", voice="aura-2-luna-en", language="bn")


@pytest.mark.parametrize(
    ("provider", "message"),
    [
        ("elevenlabs", "No ElevenLabs API key"),
        ("openrouter", "No OpenRouter API key"),
        ("deepgram", "No Deepgram API key"),
    ],
)
def test_missing_key(provider, message):
    def handler(request):
        raise AssertionError("no request expected")

    with pytest.raises(PreviewError, match=message) as exc_info:
        _run(handler, _settings(), provider=provider)
    assert exc_info.value.status_code == 400


def test_empty_voice():
    with pytest.raises(PreviewError, match="Choose a voice"):
        _run(lambda r: httpx.Response(200), _settings(), provider="elevenlabs", voice=" ")


def test_route_returns_audio(api, monkeypatch):
    calls = []

    async def fake_synthesize(**kwargs):
        calls.append(kwargs)
        return _MP3

    monkeypatch.setattr(voice_preview, "synthesize", fake_synthesize)
    response = api.post(
        "/api/agent-config/voice-preview",
        json={"stt_tts_provider": "openrouter", "voice": "v", "model": "m", "language": "bn"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == _MP3
    assert calls[0]["provider"] == "openrouter"
    assert calls[0]["language"] == "bn"


def test_route_maps_preview_errors(api, monkeypatch):
    async def fake_synthesize(**kwargs):
        raise PreviewError("Deepgram's Aura voices are English-only", 400)

    monkeypatch.setattr(voice_preview, "synthesize", fake_synthesize)
    response = api.post(
        "/api/agent-config/voice-preview",
        json={"stt_tts_provider": "deepgram", "voice": "aura-2-luna-en", "language": "bn"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Deepgram's Aura voices are English-only"
