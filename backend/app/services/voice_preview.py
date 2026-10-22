"""A short sample line spoken by a voice, so the dashboard can audition a voice,
model and provider before saving them. Returns mp3 bytes.

Each provider is called over plain REST with the same keys a call would use:
ElevenLabs tries ELEVENLABS_API_KEYS in order (a spent key moves on to the next),
OpenRouter uses the agent's OpenRouter key, Deepgram DEEPGRAM_API_KEY. Every
preview costs the same credits as speaking the line on a call."""

from typing import Literal

import httpx

from app.agent.elevenlabs_keys import API_BASE_URL as ELEVENLABS_API_URL
from app.agent.elevenlabs_keys import key_tail
from app.config import Settings
from app.services import agent_config_service
from app.services.agent_config_service import ResolvedAgentConfig

Language = Literal["en", "bn"]

# Numbers spelled out, as speak_numbers_as_words does for the agent's replies.
_SAMPLES: dict[Language, str] = {
    "en": (
        "Hi! This is {agent_name} from {agency_name}. I found a lovely three-bedroom flat "
        "in Gulshan for twenty-five lakh taka. Would you like to visit it this Friday?"
    ),
    "bn": (
        "আসসালামু আলাইকুম! আমি {agency_name} থেকে {agent_name} বলছি। গুলশানে তিন বেডরুমের "
        "একটা সুন্দর ফ্ল্যাট পেয়েছি, দাম পঁচিশ লাখ টাকা। এই শুক্রবার দেখতে আসবেন?"
    ),
}

_TIMEOUT = httpx.Timeout(30, connect=10)

# Upstream outages are reported as 503, never 502/504: Cloudflare (the dashboard's
# tunnel) swaps an origin 502/504 for its own HTML page, hiding the message.
_UNAVAILABLE = 503
_REFUSED = 400

_LIBRARY_VOICE_HINT = (
    " Pick one of the premade voices from the list, or switch to ElevenLabs via OpenRouter,"
    " which can use library voices."
)


class PreviewError(Exception):
    """The preview can't be made; the message is safe to show in the dashboard."""

    def __init__(self, message: str, status_code: int = _UNAVAILABLE) -> None:
        super().__init__(message)
        self.status_code = status_code


def sample_text(language: Language, config: ResolvedAgentConfig) -> str:
    return _SAMPLES[language].format(
        agent_name=config.assistant_name, agency_name=config.agency_name
    )


def _upstream_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or response.reason_phrase
    detail = body.get("detail") or body.get("error") or body.get("err_msg") or body
    if isinstance(detail, dict):
        detail = detail.get("message") or detail.get("status") or detail
    return str(detail)[:400]


def _status_for(upstream_status: int) -> int:
    """A 4xx from the provider means this request can't work as sent (bad voice,
    plan limits, spent credits); anything else is the provider being unavailable."""
    return _REFUSED if 400 <= upstream_status < 500 else _UNAVAILABLE


async def _elevenlabs(
    client: httpx.AsyncClient, settings: Settings, voice: str, model: str, text: str
) -> bytes:
    keys = settings.elevenlabs_keys
    if not keys:
        raise PreviewError("No ElevenLabs API key is set (ELEVENLABS_API_KEYS)", 400)
    failures: list[tuple[str, int, str]] = []
    for key in keys:
        response = await client.post(
            f"{ELEVENLABS_API_URL}/text-to-speech/{voice}",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": key},
            json={"text": text, "model_id": model},
        )
        if response.status_code == 200:
            return response.content
        message = _upstream_message(response)
        if response.status_code in (400, 404, 422):
            # The voice or model itself is wrong; another key won't help.
            raise PreviewError(f"ElevenLabs refused it: {message}", _REFUSED)
        # Spent credits, or a plan limit (e.g. library voices on a free account):
        # another key may still work.
        failures.append((key, response.status_code, message))

    messages = list(dict.fromkeys(message for _key, _status, message in failures))
    if len(messages) == 1:
        text = f"ElevenLabs refused it on every key: {messages[0]}"
    else:
        text = "Every ElevenLabs key failed. " + "; ".join(
            f"key {key_tail(key)}: {message}" for key, _status, message in failures
        )
    if any("library voice" in message.lower() for message in messages):
        text += _LIBRARY_VOICE_HINT
    status = (
        _REFUSED
        if all(_status_for(code) == _REFUSED for _key, code, _message in failures)
        else _UNAVAILABLE
    )
    raise PreviewError(text, status)


async def _openrouter(
    client: httpx.AsyncClient,
    settings: Settings,
    config: ResolvedAgentConfig,
    voice: str,
    model: str,
    text: str,
) -> bytes:
    key = agent_config_service.embedding_api_key(config, settings)
    if not key:
        raise PreviewError("No OpenRouter API key is set (OPENROUTER_API_KEY)", 400)
    response = await client.post(
        f"{settings.openrouter_base_url}/audio/speech",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "input": text, "voice": voice, "response_format": "mp3"},
    )
    if response.status_code != 200:
        status = _status_for(response.status_code)
        raise PreviewError(f"OpenRouter refused it: {_upstream_message(response)}", status)
    return response.content


async def _deepgram(client: httpx.AsyncClient, settings: Settings, model: str, text: str) -> bytes:
    if not settings.deepgram_key:
        raise PreviewError("No Deepgram API key is set (DEEPGRAM_API_KEY)", 400)
    response = await client.post(
        "https://api.deepgram.com/v1/speak",
        params={"model": model, "encoding": "mp3"},
        headers={"Authorization": f"Token {settings.deepgram_key}"},
        json={"text": text},
    )
    if response.status_code != 200:
        status = _status_for(response.status_code)
        raise PreviewError(f"Deepgram refused it: {_upstream_message(response)}", status)
    return response.content


async def synthesize(
    *,
    settings: Settings,
    config: ResolvedAgentConfig,
    provider: str,
    voice: str,
    model: str | None,
    language: Language,
    client: httpx.AsyncClient | None = None,
) -> bytes:
    """mp3 of the sample line. `voice` is the ElevenLabs voice id, or the
    Deepgram Aura model (which is the voice). `model` None = the provider's default."""
    voice = voice.strip()
    if not voice:
        raise PreviewError("Choose a voice first", 400)
    if provider == "deepgram" and language == "bn":
        raise PreviewError("Deepgram's Aura voices are English-only", 400)
    text = sample_text(language, config)
    model = (model or "").strip() or agent_config_service.default_elevenlabs_tts_model(
        provider, settings
    )

    if client is None:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as owned:
            return await synthesize(
                settings=settings, config=config, provider=provider, voice=voice,
                model=model, language=language, client=owned,
            )
    try:
        if provider == "deepgram":
            return await _deepgram(client, settings, voice, text)
        if provider == "openrouter":
            return await _openrouter(client, settings, config, voice, model, text)
        return await _elevenlabs(client, settings, voice, model, text)
    except httpx.TimeoutException as exc:
        raise PreviewError("The voice service took too long to answer", _UNAVAILABLE) from exc
    except httpx.HTTPError as exc:
        raise PreviewError(f"Couldn't reach the voice service: {exc.__class__.__name__}") from exc
