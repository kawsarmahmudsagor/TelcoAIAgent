"""ElevenLabs key rotation: config parsing, the pre-call usage check, the fail-fast
STT stream, and the STT/TTS fallback chains entrypoint builds from the keys."""

import asyncio
from types import SimpleNamespace

import aiohttp
import pytest
from livekit import rtc
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, APIStatusError
from livekit.agents import stt as stt_utils
from livekit.agents import tts as tts_utils
from livekit.plugins.elevenlabs.stt import SpeechStream

from app.agent import elevenlabs_keys, openrouter_audio
from app.agent.elevenlabs_keys import FailFastElevenLabsSTT, is_spent, usable_keys
from app.agent.entrypoint import _build_stt_and_tts, _elevenlabs_keys_for_call
from app.agent.openrouter_audio import OpenRouterSTT, OpenRouterTTS
from app.agent.sentence_tokenizer import SentenceTokenizer as BanglaSentenceTokenizer
from app.config import Settings

_ENV_VARS = (
    "ELEVENLABS_API_KEYS",
    "ELEVENLABS_API_KEY",
    "DEEPGRAM_API_KEY",
    "STT_TTS_PROVIDER",
    "ELEVENLABS_STT_MODEL",
    "ELEVENLABS_STT_SILENCE_SECS",
    "ELEVENLABS_PROVIDER",
    "ELEVENLABS_OPENROUTER_TTS_MODEL",
    "ELEVENLABS_OPENROUTER_STT_MODEL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
)


@pytest.fixture
def make_settings(monkeypatch):
    """Settings built only from the given values -- never the real .env keys."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)

    def _make(**values) -> Settings:
        return Settings(_env_file=None, **values)

    return _make


# ---- config ----


def test_keys_parsed_in_order_with_legacy_key_last(make_settings):
    s = make_settings(elevenlabs_api_keys=" k1, k2 ,,k3 ", elevenlabs_api_key="k4")
    assert s.elevenlabs_keys == ["k1", "k2", "k3", "k4"]


def test_keys_deduped_and_placeholders_ignored(make_settings):
    s = make_settings(elevenlabs_api_keys="k1,changeme,k2,k1", elevenlabs_api_key="k2")
    assert s.elevenlabs_keys == ["k1", "k2"]


def test_legacy_single_key_still_works(make_settings):
    assert make_settings(elevenlabs_api_key="only").elevenlabs_keys == ["only"]
    assert make_settings(elevenlabs_api_key="changeme").elevenlabs_keys == []


def test_deepgram_placeholder_is_no_key(make_settings):
    assert make_settings(deepgram_api_key="changeme").deepgram_key == ""
    assert make_settings(deepgram_api_key=" dg ").deepgram_key == "dg"


# ---- usage check ----


@pytest.mark.parametrize(
    ("payload", "spent"),
    [
        ({"character_limit": 10000, "character_count": 2000}, False),
        ({"character_limit": 10000, "character_count": 9001}, True),
        ({"character_limit": 10000, "character_count": 9000}, False),
        ({"character_limit": 10000, "character_count": 10000}, True),
        ({"character_limit": None}, False),
        (None, False),
    ],
)
def test_is_spent(payload, spent):
    assert is_spent(payload, 1000) is spent


def _fake_fetch(responses: dict[tuple[str, str], object]):
    """responses[(key, "sub"|"voice")] is (status, body) or an exception to raise."""

    async def fetch(key: str, path: str):
        result = responses.get((key, "sub" if path == "/user/subscription" else "voice"))
        if isinstance(result, BaseException):
            raise result
        return result or (200, {})

    return fetch


def test_usable_keys_orders_and_drops():
    plenty = (200, {"character_limit": 10000, "character_count": 100})
    nearly_out = (200, {"character_limit": 10000, "character_count": 9950})
    fetch = _fake_fetch(
        {
            ("low", "sub"): nearly_out,
            ("good1", "sub"): plenty,
            ("invalid", "sub"): (401, {"detail": {"status": "invalid_api_key"}}),
            ("novoice", "sub"): plenty,
            ("novoice", "voice"): (404, {"detail": {"status": "voice_not_found"}}),
            ("timeout", "sub"): asyncio.TimeoutError(),
            ("restricted", "sub"): (401, {"detail": {"status": "missing_permissions"}}),
            ("good2", "sub"): plenty,
        }
    )
    keys = ["low", "good1", "invalid", "novoice", "timeout", "restricted", "good2"]
    result = asyncio.run(usable_keys(keys, "voice", 1000, fetch))
    assert result == ["good1", "timeout", "restricted", "good2", "low"]


def test_usable_keys_keeps_all_nearly_empty_keys():
    nearly_out = (200, {"character_limit": 10000, "character_count": 9999})
    fetch = _fake_fetch({("a", "sub"): nearly_out, ("b", "sub"): nearly_out})
    assert asyncio.run(usable_keys(["a", "b"], "voice", 1000, fetch)) == ["a", "b"]


def test_usable_keys_empty():
    assert asyncio.run(usable_keys([], "voice", 1000, _fake_fetch({}))) == []


# ---- fail-fast STT ----


class _FakeWS:
    """Just enough of aiohttp's websocket for the plugin's send/recv loops."""

    close_code = 1000

    def __init__(self) -> None:
        self._inbox: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def send_str(self, data: str) -> None:
        pass

    async def receive(self):
        return await self._inbox.get()

    async def close(self) -> bool:
        if not self.closed:
            self.closed = True
            self._inbox.put_nowait(SimpleNamespace(type=aiohttp.WSMsgType.CLOSE, data=None, extra=None))
        return True


def test_quota_exceeded_fails_the_stt_stream(monkeypatch):
    ws = _FakeWS()

    async def fake_connect(self):
        return ws

    monkeypatch.setattr(SpeechStream, "_connect_ws", fake_connect)

    async def run():
        async with aiohttp.ClientSession() as session:
            stt = FailFastElevenLabsSTT(
                api_key="x", model="scribe_v2_realtime", http_session=session
            )
            stream = stt.stream()
            for _ in range(50):
                if stream._ws is not None:
                    break
                await asyncio.sleep(0.01)
            assert stream._ws is ws
            stream._process_stream_event({"message_type": "quota_exceeded", "message": "x"})
            with pytest.raises(APIStatusError) as exc_info:
                async for _ in stream:
                    pass
            await stream.aclose()
            return exc_info.value

    err = asyncio.run(run())
    assert err.status_code == 401
    assert err.retryable is False
    assert ws.closed


def test_ordinary_stt_messages_still_handled(monkeypatch):
    called = []
    monkeypatch.setattr(
        SpeechStream, "_process_stream_event", lambda self, data: called.append(data)
    )
    stream = elevenlabs_keys._FailFastSpeechStream.__new__(elevenlabs_keys._FailFastSpeechStream)
    stream._process_stream_event({"message_type": "partial_transcript"})
    assert called == [{"message_type": "partial_transcript"}]
    assert stream._fatal is None


def _bare_stream(server_vad=NOT_GIVEN) -> elevenlabs_keys._FailFastSpeechStream:
    """A stream with just the state _connect_ws/_process_stream_event read -- no
    event loop, no socket."""
    stt = FailFastElevenLabsSTT(api_key="x", model="scribe_v2_realtime", server_vad=server_vad)
    stream = elevenlabs_keys._FailFastSpeechStream.__new__(elevenlabs_keys._FailFastSpeechStream)
    stream._opts = stt._opts
    stream._language = None
    stream._conn_options = DEFAULT_API_CONNECT_OPTIONS
    stream._speaking = False
    stream._start_time_offset = 0.0
    return stream


def test_server_vad_connects_with_vad_commits():
    urls = []

    async def ws_connect(url, headers):
        urls.append(url)
        return object()

    stream = _bare_stream({"vad_silence_threshold_secs": 0.8})
    stream._session = SimpleNamespace(ws_connect=ws_connect)
    asyncio.run(stream._connect_ws())
    assert "commit_strategy=vad" in urls[0]
    assert "vad_silence_threshold_secs=0.8" in urls[0]


@pytest.mark.parametrize(
    ("server_vad", "expected"),
    [
        (
            {"vad_silence_threshold_secs": 0.8},
            ["START_OF_SPEECH", "FINAL_TRANSCRIPT", "END_OF_SPEECH"],
        ),
        # Manual commits (no server_vad): the speech segment never ends.
        (NOT_GIVEN, ["START_OF_SPEECH", "FINAL_TRANSCRIPT"]),
    ],
)
def test_committed_transcript_events(server_vad, expected):
    events = []
    stream = _bare_stream(server_vad)
    stream._event_ch = SimpleNamespace(send_nowait=events.append)
    # "committed_transcript_with_timestamps" instead if include_timestamps is turned on.
    stream._process_stream_event({"message_type": "committed_transcript", "text": "hi"})
    assert [e.type.name for e in events] == expected
    assert events[1].alternatives[0].text == "hi"
    assert stream._speaking is (server_vad is NOT_GIVEN)


# ---- fallback chains ----


class _FakeChunkedStream(tts_utils.ChunkedStream):
    async def _run(self, output_emitter: tts_utils.AudioEmitter) -> None:
        tts = self._tts
        tts.calls += 1
        if tts.fail:
            raise APIStatusError("quota_exceeded", status_code=401)
        output_emitter.initialize(
            request_id="r", sample_rate=16000, num_channels=1, mime_type="audio/pcm"
        )
        output_emitter.push(b"\x00\x00" * 1600)
        output_emitter.flush()


class _FakeTTS(tts_utils.TTS):
    def __init__(self, *, fail: bool) -> None:
        super().__init__(
            capabilities=tts_utils.TTSCapabilities(streaming=False),
            sample_rate=16000,
            num_channels=1,
        )
        self.fail = fail
        self.calls = 0

    def synthesize(self, text, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):
        return _FakeChunkedStream(tts=self, input_text=text, conn_options=conn_options)


def test_tts_chain_switches_to_next_key_on_quota():
    dead, alive = _FakeTTS(fail=True), _FakeTTS(fail=False)

    async def run():
        chain = tts_utils.FallbackAdapter(
            [tts_utils.StreamAdapter(tts=dead), tts_utils.StreamAdapter(tts=alive)],
            max_retry_per_tts=1,
        )
        try:
            first = [f async for f in chain.synthesize("hello")]
            second = [f async for f in chain.synthesize("again")]
            return chain, first, second
        finally:
            await chain.aclose()

    chain, first, second = asyncio.run(run())
    assert first and second
    # Both turns served by the second key; the dead one is only background-probed.
    assert alive.calls == 2
    assert chain._status[0].available is False
    assert chain._status[1].available is True


class _FakeSpeechStream(stt_utils.RecognizeStream):
    async def _run(self) -> None:
        if self._stt.fail:
            raise APIStatusError("quota_exceeded", status_code=401)
        async for _ in self._input_ch:
            self._event_ch.send_nowait(
                stt_utils.SpeechEvent(
                    type=stt_utils.SpeechEventType.FINAL_TRANSCRIPT,
                    alternatives=[stt_utils.SpeechData(language="en", text="hello")],
                )
            )
            return


class _FakeSTT(stt_utils.STT):
    def __init__(self, *, fail: bool) -> None:
        super().__init__(
            capabilities=stt_utils.STTCapabilities(streaming=True, interim_results=False)
        )
        self.fail = fail

    async def _recognize_impl(self, buffer, *, language, conn_options):
        raise NotImplementedError

    def stream(self, *, language=NOT_GIVEN, conn_options=DEFAULT_API_CONNECT_OPTIONS):
        return _FakeSpeechStream(stt=self, conn_options=conn_options)


def test_stt_chain_switches_to_next_key_on_quota():
    async def run():
        chain = stt_utils.FallbackAdapter(
            [_FakeSTT(fail=True), _FakeSTT(fail=False)], max_retry_per_stt=1
        )
        stream = chain.stream()
        frame = rtc.AudioFrame(b"\x00\x00" * 160, sample_rate=16000, num_channels=1, samples_per_channel=160)

        async def feed():
            for _ in range(100):
                stream.push_frame(frame)
                await asyncio.sleep(0.01)

        feeder = asyncio.create_task(feed())
        try:
            async def first_final():
                async for ev in stream:
                    if ev.type == stt_utils.SpeechEventType.FINAL_TRANSCRIPT:
                        return ev

            ev = await asyncio.wait_for(first_final(), timeout=5)
        finally:
            feeder.cancel()
            await stream.aclose()
            await chain.aclose()
        return chain, ev

    chain, ev = asyncio.run(run())
    assert ev.alternatives[0].text == "hello"
    assert chain._status[0].available is False


# ---- builder ----


_CONFIG = SimpleNamespace(
    stt_tts_provider="elevenlabs",
    elevenlabs_voice_id="voice",
    elevenlabs_tts_model="eleven_v4_turbo",
    deepgram_tts_model="aura-2-thalia-en",
)


def test_builder_chains_every_key_then_deepgram(make_settings):
    s = make_settings(deepgram_api_key="dg")
    stt, tts = _build_stt_and_tts(s, _CONFIG, ["key-aaaa", "key-bbbb", "key-cccc"])
    assert isinstance(stt, stt_utils.FallbackAdapter)
    assert isinstance(tts, tts_utils.FallbackAdapter)
    labels = ["elevenlabs …aaaa", "elevenlabs …bbbb", "elevenlabs …cccc", "deepgram"]
    assert [i.label for i in stt._stt_instances] == labels
    assert [i.label for i in tts._tts_instances] == labels
    assert isinstance(stt._stt_instances[0], FailFastElevenLabsSTT)
    assert tts.capabilities.aligned_transcript is True
    assert tts.sample_rate == tts._tts_instances[0].sample_rate


def test_builder_single_key_is_not_wrapped(make_settings):
    stt, tts = _build_stt_and_tts(make_settings(), _CONFIG, ["key-aaaa"])
    assert isinstance(stt, FailFastElevenLabsSTT)
    assert isinstance(tts, tts_utils.StreamAdapter)
    assert isinstance(tts._sentence_tokenizer, BanglaSentenceTokenizer)


def test_builder_sets_scribe_server_vad(make_settings):
    single, _ = _build_stt_and_tts(make_settings(), _CONFIG, ["key-aaaa"])
    assert single._opts.server_vad == {"vad_silence_threshold_secs": 0.8}

    s = make_settings(deepgram_api_key="dg", elevenlabs_stt_silence_secs=1.2)
    chain, _ = _build_stt_and_tts(s, _CONFIG, ["key-aaaa", "key-bbbb"])
    scribes = [i for i in chain._stt_instances if isinstance(i, FailFastElevenLabsSTT)]
    assert len(scribes) == 2
    assert all(i._opts.server_vad == {"vad_silence_threshold_secs": 1.2} for i in scribes)


def test_silence_secs_out_of_range_is_rejected(make_settings):
    with pytest.raises(ValueError):
        make_settings(elevenlabs_stt_silence_secs=0.1)


def test_builder_no_keys_falls_back_to_deepgram(make_settings):
    stt, tts = _build_stt_and_tts(make_settings(deepgram_api_key="dg"), _CONFIG, [])
    assert stt.label == "deepgram"
    assert tts.label == "deepgram"


def test_builder_no_provider_raises(make_settings):
    with pytest.raises(RuntimeError, match="no STT/TTS provider"):
        _build_stt_and_tts(make_settings(deepgram_api_key="changeme"), _CONFIG, [])


def test_builder_placeholder_deepgram_not_appended(make_settings):
    stt, _ = _build_stt_and_tts(
        make_settings(deepgram_api_key="changeme"), _CONFIG, ["key-aaaa", "key-bbbb"]
    )
    assert [i.label for i in stt._stt_instances] == ["elevenlabs …aaaa", "elevenlabs …bbbb"]


def test_builder_rejects_non_realtime_stt_model(make_settings):
    s = make_settings(elevenlabs_stt_model="scribe_v1")
    with pytest.raises(RuntimeError, match="not a realtime model"):
        _build_stt_and_tts(s, _CONFIG, ["key-aaaa"])


# ---- voice provider "openrouter" ----


_OR_CONFIG = SimpleNamespace(
    stt_tts_provider="openrouter",
    elevenlabs_voice_id="voice",
    elevenlabs_tts_model="elevenlabs/eleven-v3",
    deepgram_tts_model="aura-2-thalia-en",
    llm_provider="gemini",
    api_key="",
)


def _openrouter_settings(make_settings, **values):
    return make_settings(openrouter_api_key="or-key", **values)


def test_openrouter_builder_needs_no_elevenlabs_keys(make_settings):
    s = _openrouter_settings(make_settings, elevenlabs_openrouter_stt_model="elevenlabs/scribe-x")
    stt, tts = _build_stt_and_tts(s, _OR_CONFIG, [])
    assert isinstance(stt, OpenRouterSTT)
    assert stt.capabilities.streaming is False
    assert stt.model == "elevenlabs/scribe-x"
    assert str(stt._client.base_url).rstrip("/") == s.openrouter_base_url
    assert isinstance(tts, tts_utils.StreamAdapter)
    assert isinstance(tts._wrapped_tts, OpenRouterTTS)
    assert isinstance(tts._sentence_tokenizer, BanglaSentenceTokenizer)
    assert tts._wrapped_tts.model == "elevenlabs/eleven-v3"


def test_openrouter_builder_falls_back_to_deepgram(make_settings):
    s = _openrouter_settings(make_settings, deepgram_api_key="dg")
    stt, tts = _build_stt_and_tts(s, _OR_CONFIG, [], vad=SimpleNamespace())
    assert isinstance(stt, stt_utils.FallbackAdapter)
    assert isinstance(tts, tts_utils.FallbackAdapter)
    labels = ["openrouter elevenlabs", "deepgram"]
    assert [i.label for i in stt._stt_instances] == labels
    assert [i.label for i in tts._tts_instances] == labels
    assert all(
        isinstance(i._sentence_tokenizer, BanglaSentenceTokenizer) for i in tts._tts_instances
    )
    assert isinstance(stt._stt_instances[0], stt_utils.StreamAdapter)
    assert tts.capabilities.aligned_transcript is True


def test_openrouter_deepgram_fallback_needs_vad(make_settings):
    s = _openrouter_settings(make_settings, deepgram_api_key="dg")
    with pytest.raises(RuntimeError, match="VAD"):
        _build_stt_and_tts(s, _OR_CONFIG, [])


def test_openrouter_without_key_raises_before_building(make_settings, monkeypatch):
    built = []
    monkeypatch.setattr(openrouter_audio, "make_openrouter_stt", lambda *a, **k: built.append(a))
    s = make_settings()
    with pytest.raises(RuntimeError, match="no OpenRouter API key"):
        _build_stt_and_tts(s, _OR_CONFIG, [])
    assert built == []


def test_openrouter_uses_dashboard_key_when_llm_is_openrouter(make_settings):
    config = SimpleNamespace(**{**vars(_OR_CONFIG), "llm_provider": "openrouter", "api_key": "dash"})
    stt, _ = _build_stt_and_tts(make_settings(), config, [])
    assert stt._client.api_key == "dash"


def test_openrouter_without_voice_raises(make_settings):
    config = SimpleNamespace(**{**vars(_OR_CONFIG), "elevenlabs_voice_id": ""})
    with pytest.raises(RuntimeError, match="no ElevenLabs voice"):
        _build_stt_and_tts(_openrouter_settings(make_settings), config, [])


def test_openrouter_skips_the_elevenlabs_key_check(make_settings, monkeypatch):
    calls = []

    async def fake_usable_keys(*args):
        calls.append(args)
        return []

    monkeypatch.setattr(elevenlabs_keys, "usable_keys", fake_usable_keys)
    s = _openrouter_settings(make_settings, elevenlabs_api_keys="k1,k2")
    assert asyncio.run(_elevenlabs_keys_for_call(s, _OR_CONFIG)) == []
    assert calls == []
