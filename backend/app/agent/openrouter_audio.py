"""ElevenLabs speech models served through OpenRouter (ELEVENLABS_PROVIDER=openrouter).

OpenRouter exposes them behind OpenAI-style endpoints: /audio/speech returns raw audio
bytes and /audio/transcriptions takes one uploaded file per request. Neither streams,
so the STT is driven per turn by the session's VAD and the TTS sentence by sentence by
a StreamAdapter.

- OpenRouterTTS: the openai plugin's TTS can't be reused -- for any model other than
  tts-1 it parses an SSE stream (OpenRouter sends plain bytes, so every turn would be
  silent) and it always sends `speed` and `stream_format`.
- OpenRouterSTT: the openai plugin's STT already sends only what OpenRouter takes
  (file, model, response_format), but each request may wait 30s for a response,
  retried 3 times. Transcription is serial, so one stuck upload would stall the call;
  this caps it.
"""

import asyncio
import dataclasses

import httpx
import openai
from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectionError,
    APIConnectOptions,
    APIStatusError,
    APITimeoutError,
    NotGivenOr,
    stt,
    tts,
)
from livekit.agents.utils import AudioBuffer, shortuuid
from livekit.plugins import openai as openai_plugin

from app.config import Settings

SAMPLE_RATE = 24000
NUM_CHANNELS = 1

# Per-attempt cap on one turn's transcription; a turn is a few seconds of audio.
_STT_TIMEOUT_S = 8.0
_STT_MAX_RETRY = 1


def _client(base_url: str, api_key: str) -> openai.AsyncClient:
    return openai.AsyncClient(base_url=base_url, api_key=api_key, max_retries=0)


class OpenRouterTTS(tts.TTS):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        voice: str,
        client: openai.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        self._model = model
        self._voice = voice
        self._owns_client = client is None
        self._client = client or _client(base_url, api_key)

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "openrouter"

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
        return _ChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()


class _ChunkedStream(tts.ChunkedStream):
    def __init__(self, *, tts: OpenRouterTTS, input_text: str, conn_options: APIConnectOptions):
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._tts: OpenRouterTTS = tts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        response = self._tts._client.audio.speech.with_streaming_response.create(
            model=self._tts._model,
            input=self.input_text,
            voice=self._tts._voice,
            response_format="mp3",
            timeout=httpx.Timeout(30, connect=self._conn_options.timeout),
        )
        try:
            async with response as stream:
                # mp3 rather than pcm: OpenRouter doesn't document the pcm sample rate,
                # and the emitter decodes mp3 and resamples it to SAMPLE_RATE.
                output_emitter.initialize(
                    # OpenRouter sends no request id header.
                    request_id=stream.request_id or shortuuid(),
                    sample_rate=SAMPLE_RATE,
                    num_channels=NUM_CHANNELS,
                    mime_type="audio/mpeg",
                )
                async for data in stream.iter_bytes():
                    output_emitter.push(data)
            output_emitter.flush()
        except openai.APITimeoutError:
            raise APITimeoutError() from None
        except openai.APIStatusError as e:
            raise APIStatusError(
                e.message, status_code=e.status_code, request_id=e.request_id, body=e.body
            ) from None
        except Exception as e:
            raise APIConnectionError() from e


class OpenRouterSTT(openai_plugin.STT):
    async def recognize(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        if conn_options.max_retry > _STT_MAX_RETRY:
            conn_options = dataclasses.replace(conn_options, max_retry=_STT_MAX_RETRY)
        return await super().recognize(buffer, language=language, conn_options=conn_options)

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        # The plugin passes its own 30s read timeout per request, overriding any
        # client timeout, so the cap has to wrap the whole call.
        try:
            return await asyncio.wait_for(
                super()._recognize_impl(buffer, language=language, conn_options=conn_options),
                _STT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            raise APITimeoutError() from None


def make_openrouter_stt(
    settings: Settings, api_key: str, *, client: openai.AsyncClient | None = None
) -> OpenRouterSTT:
    return OpenRouterSTT(
        model=settings.elevenlabs_openrouter_stt_model,
        # No language hint: Scribe detects it per turn, as on the free path.
        detect_language=True,
        use_realtime=False,
        client=client or _client(settings.openrouter_base_url, api_key),
    )
