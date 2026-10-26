"""Several ElevenLabs API keys (e.g. one per free account) used as a fallback chain.

entrypoint wraps one STT/TTS per key in livekit's FallbackAdapter, which switches to
the next key the moment one fails mid-call. Two pieces live here:

- usable_keys(): each job runs in its own process, so nothing remembers that a key
  ran dry on an earlier call. Before a call, ask ElevenLabs how many credits each
  key has left and try the near-empty ones last, so the call doesn't start on a dead
  key and lose its first turn to the switch.
- FailFastElevenLabsSTT: the plugin's realtime STT only *logs* a quota_exceeded or
  auth_error message (its receive loop swallows the exception), so the stream stays
  open on a dead key and the FallbackAdapter never switches. This subclass turns
  those messages into a stream failure.
- BatchElevenLabsSTT: Scribe v2 on a whole turn (ELEVENLABS_STT_MODEL=scribe_v2),
  with a cap on each request the plugin doesn't have.
"""

import asyncio
import dataclasses
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIConnectOptions, APIError
from livekit.agents import APIStatusError, APITimeoutError, NotGivenOr, stt
from livekit.agents.utils import AudioBuffer
from livekit.agents.utils import is_given
from livekit.plugins import elevenlabs
from livekit.plugins.elevenlabs.stt import SpeechStream

logger = logging.getLogger("agent.elevenlabs_keys")

API_BASE_URL = "https://api.elevenlabs.io/v1"
# Runs before the greeting, so keep it short; a key whose check times out is kept.
_CHECK_TIMEOUT_S = 1.5

# (api_key, path) -> (HTTP status, parsed JSON body or None)
Fetch = Callable[[str, str], Awaitable[tuple[int, Any]]]


def key_tail(key: str) -> str:
    """How a key shows up in logs -- never the whole secret."""
    return f"…{key[-4:]}"


def is_spent(subscription: Any, min_remaining: int) -> bool:
    """True when a /user/subscription payload has fewer than min_remaining credits left."""
    if not isinstance(subscription, dict):
        return False
    limit = subscription.get("character_limit")
    used = subscription.get("character_count")
    if not isinstance(limit, int) or not isinstance(used, int):
        return False
    return limit - used < min_remaining


def _detail_status(body: Any) -> str | None:
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail.get("status") if isinstance(detail, dict) else None


async def _classify(key: str, voice_id: str, min_remaining: int, fetch: Fetch) -> str:
    """"good", "low" (few credits left: try last) or "drop" (can't serve this call).
    Anything inconclusive -- timeout, network error, a key restricted from reading
    its own subscription -- counts as good; the fallback chain still catches it."""
    sub, voice = await asyncio.gather(
        fetch(key, "/user/subscription"),
        fetch(key, f"/voices/{voice_id}") if voice_id else asyncio.sleep(0, (200, None)),
        return_exceptions=True,
    )
    if isinstance(sub, BaseException):
        logger.warning("elevenlabs key %s: usage check failed (%r), keeping it", key_tail(key), sub)
    else:
        status, body = sub
        if status == 401 and _detail_status(body) != "missing_permissions":
            logger.warning(
                "elevenlabs key %s rejected (%s), skipping it", key_tail(key), _detail_status(body)
            )
            return "drop"
        if status == 200 and is_spent(body, min_remaining):
            logger.info("elevenlabs key %s is nearly out of credits, trying it last", key_tail(key))
            return "low"
    if not isinstance(voice, BaseException) and voice[0] in (400, 404):
        logger.warning(
            "elevenlabs key %s can't use voice %s, skipping it", key_tail(key), voice_id
        )
        return "drop"
    return "good"


def _http_fetch(session: aiohttp.ClientSession) -> Fetch:
    async def fetch(key: str, path: str) -> tuple[int, Any]:
        async with session.get(f"{API_BASE_URL}{path}", headers={"xi-api-key": key}) as resp:
            try:
                body = await resp.json(content_type=None)
            except ValueError:
                body = None
            return resp.status, body

    return fetch


async def usable_keys(
    keys: list[str], voice_id: str, min_remaining: int, fetch: Fetch | None = None
) -> list[str]:
    """`keys` reordered for this call: keys with credits first, nearly-empty ones
    after them (a key with a few hundred credits beats no call), keys that are
    invalid or can't use `voice_id` dropped. Order is kept within each group."""
    if not keys:
        return []
    if fetch is None:
        timeout = aiohttp.ClientTimeout(total=_CHECK_TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            return await usable_keys(keys, voice_id, min_remaining, _http_fetch(session))

    verdicts = await asyncio.gather(*(_classify(k, voice_id, min_remaining, fetch) for k in keys))
    good = [k for k, v in zip(keys, verdicts) if v == "good"]
    low = [k for k, v in zip(keys, verdicts) if v == "low"]
    return good + low


# Realtime STT messages that mean this key can't transcribe any more.
_FATAL_STT_MESSAGES = ("quota_exceeded", "auth_error")


class _FailFastSpeechStream(SpeechStream):
    _ws: aiohttp.ClientWebSocketResponse | None = None
    _fatal: APIStatusError | None = None
    _close_task: asyncio.Task | None = None

    async def _connect_ws(self) -> aiohttp.ClientWebSocketResponse:
        self._ws = await super()._connect_ws()
        return self._ws

    def _process_stream_event(self, data: dict) -> None:
        message_type = data.get("message_type")
        if message_type not in _FATAL_STT_MESSAGES:
            super()._process_stream_event(data)
            return
        # 401 makes it non-retryable, so the FallbackAdapter moves on immediately.
        self._fatal = APIStatusError(
            f"ElevenLabs STT {message_type}: {data.get('message', '')}", status_code=401
        )
        logger.error("ElevenLabs STT %s, closing the stream", message_type)
        if self._ws is not None and self._close_task is None:
            # Closing the socket wakes the plugin's receive loop, which raises and
            # runs the plugin's own cleanup.
            self._close_task = asyncio.ensure_future(self._ws.close())

    async def _run(self) -> None:
        try:
            await super()._run()
        except APIError:
            if self._fatal is not None:
                raise self._fatal from None
            raise


class FailFastElevenLabsSTT(elevenlabs.STT):
    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> SpeechStream:
        # Mirrors elevenlabs.STT.stream(), swapping in the fail-fast stream.
        stream = _FailFastSpeechStream(
            stt=self,
            opts=self._opts,
            conn_options=conn_options,
            language=language if is_given(language) else self._opts.language_code,
            http_session=self._ensure_session(),
        )
        self._streams.add(stream)
        return stream


# Per-attempt cap on one turn's transcription; a turn is a few seconds of audio.
_BATCH_STT_TIMEOUT_S = 8.0
_BATCH_STT_MAX_RETRY = 1


class BatchElevenLabsSTT(elevenlabs.STT):
    """The plugin's Scribe v2 (non-realtime) STT, transcribing each turn whole
    once the session's VAD has cut it, so Scribe detects the language from all
    of it: the realtime model can write Bangla as Turkish. Its request has no
    timeout and may be retried 3 times, and transcription is serial, so one
    stuck upload would stall the call; capped as openrouter_audio.OpenRouterSTT is."""

    async def recognize(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        if conn_options.max_retry > _BATCH_STT_MAX_RETRY:
            conn_options = dataclasses.replace(conn_options, max_retry=_BATCH_STT_MAX_RETRY)
        return await super().recognize(buffer, language=language, conn_options=conn_options)

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        try:
            return await asyncio.wait_for(
                super()._recognize_impl(buffer, language=language, conn_options=conn_options),
                _BATCH_STT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            raise APITimeoutError() from None
