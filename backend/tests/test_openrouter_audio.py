"""ElevenLabs through OpenRouter: what the TTS and STT send, and how they fail.
Requests go to an httpx.MockTransport, never the network."""

import asyncio
import json
from pathlib import Path

import httpx
import openai
import pytest
from livekit import rtc
from livekit.agents import APIConnectOptions, APIError, APIStatusError, APITimeoutError

from app.agent import openrouter_audio
from app.agent.openrouter_audio import OpenRouterTTS, make_openrouter_stt
from app.config import Settings

_BASE_URL = "https://openrouter.ai/api/v1"
_MP3 = (Path(__file__).parent / "fixtures" / "tone.mp3").read_bytes()
_NO_RETRY = APIConnectOptions(max_retry=0)


def _client(handler) -> openai.AsyncClient:
    return openai.AsyncClient(
        base_url=_BASE_URL,
        api_key="or-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _tts(handler) -> OpenRouterTTS:
    return OpenRouterTTS(
        api_key="or-key",
        base_url=_BASE_URL,
        model="elevenlabs/eleven-v4-turbo",
        voice="EXAVITQu4vr4xnSDxMaL",
        client=_client(handler),
    )


async def _synthesize(tts: OpenRouterTTS, conn_options=_NO_RETRY) -> list:
    return [f async for f in tts.synthesize("Hello", conn_options=conn_options)]


# ---- TTS ----


def test_tts_sends_only_what_openrouter_documents():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=_MP3, headers={"content-type": "audio/mpeg"})

    frames = asyncio.run(_synthesize(_tts(handler)))
    assert frames
    assert frames[0].frame.sample_rate == openrouter_audio.SAMPLE_RATE
    (request,) = seen
    assert request.url == f"{_BASE_URL}/audio/speech"
    assert request.headers["authorization"] == "Bearer or-key"
    assert json.loads(request.content) == {
        "model": "elevenlabs/eleven-v4-turbo",
        "input": "Hello",
        "voice": "EXAVITQu4vr4xnSDxMaL",
        "response_format": "mp3",
    }


@pytest.mark.parametrize("status", [402, 500])
def test_tts_error_status_raises(status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "nope"}})

    with pytest.raises(APIStatusError) as exc_info:
        asyncio.run(_synthesize(_tts(handler)))
    assert exc_info.value.status_code == status


def test_tts_empty_audio_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"", headers={"content-type": "audio/mpeg"})

    with pytest.raises(APIError):
        asyncio.run(_synthesize(_tts(handler)))


# ---- STT ----


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        openrouter_base_url=_BASE_URL,
        elevenlabs_openrouter_stt_model="elevenlabs/scribe-v2",
    )


def _frame() -> rtc.AudioFrame:
    return rtc.AudioFrame(
        b"\x00\x00" * 1600, sample_rate=16000, num_channels=1, samples_per_channel=1600
    )


def _form_fields(request: httpx.Request) -> dict[str, str]:
    """The non-file fields of a multipart body."""
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields = {}
    for part in request.content.split(b"--" + boundary):
        head, _, body = part.partition(b"\r\n\r\n")
        if b'name="' not in head or b"filename=" in head:
            continue
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        fields[name] = body.rstrip(b"\r\n").decode()
    return fields


def test_stt_sends_only_file_model_and_format():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "hi"})

    stt = make_openrouter_stt(_settings(), "or-key", client=_client(handler))
    assert stt.capabilities.streaming is False
    event = asyncio.run(stt.recognize([_frame()], conn_options=_NO_RETRY))

    assert event.alternatives[0].text == "hi"
    (request,) = seen
    assert request.url == f"{_BASE_URL}/audio/transcriptions"
    assert b'filename="file.wav"' in request.content
    assert _form_fields(request) == {"model": "elevenlabs/scribe-v2", "response_format": "json"}


def test_stt_timeout_is_capped(monkeypatch):
    monkeypatch.setattr(openrouter_audio, "_STT_TIMEOUT_S", 0.05)

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={"text": "late"})

    stt = make_openrouter_stt(_settings(), "or-key", client=_client(handler))
    with pytest.raises(APITimeoutError):
        asyncio.run(stt.recognize([_frame()], conn_options=_NO_RETRY))


def test_stt_retries_at_most_once(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, json={"error": {"message": "busy"}})

    stt = make_openrouter_stt(_settings(), "or-key", client=_client(handler))
    options = APIConnectOptions(max_retry=3, retry_interval=0)
    with pytest.raises(APIError):
        asyncio.run(stt.recognize([_frame()], conn_options=options))
    assert len(calls) == 2
