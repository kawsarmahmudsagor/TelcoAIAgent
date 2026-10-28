"""The filler audio cache: what may be reused for what, and the TTS wrapper that
plays a cached line without a request. The wrapped TTS is a fake."""

import asyncio

import numpy as np
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, tts

from app.agent.audio_cache import AudioCache, AudioCachingTTS, cache_entities

_VOICE = "voice:eleven_v4_turbo"
_PCM = np.arange(240, dtype=np.int16).tobytes()


def _cache(tmp_path) -> AudioCache:
    return AudioCache(tmp_path)


def test_a_saved_line_is_found_again_and_survives_a_restart(tmp_path):
    cache = _cache(tmp_path)
    cache.save("জি, একটু চেক করছি।", _PCM, 24000, 1, _VOICE)
    item, ratio = cache.find("জি, একটু চেক করছি", _VOICE, 24000)
    assert ratio == 1.0 and item.pcm_data == _PCM
    reloaded = _cache(tmp_path)
    item, _ = reloaded.find("জি, একটু চেক করছি।", _VOICE, 24000)
    assert item.pcm_data == _PCM


def test_only_the_same_words_are_reused(tmp_path):
    cache = _cache(tmp_path)
    cache.save("ঠিক আছে, ডাটা প্যাকেজগুলো চেক করছি।", _PCM, 24000, 1, _VOICE)
    cache.save("৫০ টাকার মধ্যে, চেক করছি।", _PCM, 24000, 1, _VOICE)
    # run_26: this line, 0.84 similar, played the line before it again.
    assert cache.find("ওকে, ডাটা প্যাকেজগুলো বের করছি।", _VOICE, 24000) is None
    assert cache.find("ডাটা প্যাকেজগুলো চেক করছি।", _VOICE, 24000) is None
    assert cache.find("মিনিট প্যাকেজগুলো চেক করছি।", _VOICE, 24000) is None
    assert cache.find("৬০ টাকার মধ্যে, চেক করছি।", _VOICE, 24000) is None
    assert cache_entities("ডাটা প্যাকেজ") != cache_entities("মিনিট প্যাকেজ")


def test_another_voice_or_sample_rate_is_never_reused(tmp_path):
    cache = _cache(tmp_path)
    cache.save("জি, একটু চেক করছি।", _PCM, 24000, 1, _VOICE)
    assert cache.find("জি, একটু চেক করছি।", "other:eleven_v4_turbo", 24000) is None
    assert cache.find("জি, একটু চেক করছি।", "voice:eleven_v3", 24000) is None
    assert cache.find("জি, একটু চেক করছি।", _VOICE, 16000) is None


class _FakeStream(tts.ChunkedStream):
    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        output_emitter.initialize(
            request_id="r", sample_rate=24000, num_channels=1, mime_type="audio/pcm"
        )
        output_emitter.push(_PCM)
        output_emitter.flush()


class _FakeTTS(tts.TTS):
    def __init__(self) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False), sample_rate=24000, num_channels=1
        )
        self.requests: list[str] = []

    def synthesize(self, text, *, conn_options=DEFAULT_API_CONNECT_OPTIONS):
        self.requests.append(text)
        return _FakeStream(tts=self, input_text=text, conn_options=conn_options)


async def _say(wrapper: AudioCachingTTS, text: str) -> bytes:
    out = bytearray()
    async with wrapper.synthesize(text) as stream:
        async for audio in stream:
            out.extend(audio.frame.data.tobytes())
    return bytes(out)


def test_a_filler_plays_from_the_cache_the_second_time(tmp_path):
    async def go():
        inner = _FakeTTS()
        wrapper = AudioCachingTTS(
            inner, cacheable=lambda text: "চেক" in text, voice_key=_VOICE, cache=_cache(tmp_path)
        )
        first = await _say(wrapper, "জি, একটু চেক করছি।")
        second = await _say(wrapper, "জি, একটু চেক করছি।")
        return inner.requests, first, second

    requests, first, second = asyncio.run(go())
    assert requests == ["জি, একটু চেক করছি।"]
    # The emitter pads the last frame with silence; the cached audio is what was played.
    assert first == second and first.startswith(_PCM)


def test_a_reply_sentence_is_never_cached(tmp_path):
    async def go():
        inner = _FakeTTS()
        cache = _cache(tmp_path)
        wrapper = AudioCachingTTS(inner, cacheable=lambda text: False, voice_key=_VOICE, cache=cache)
        await _say(wrapper, "আপনার ব্যালেন্স ৫০ টাকা।")
        await _say(wrapper, "আপনার ব্যালেন্স ৫০ টাকা।")
        return inner.requests, len(cache)

    requests, cached = asyncio.run(go())
    assert requests == ["আপনার ব্যালেন্স ৫০ টাকা।"] * 2
    assert cached == 0


def test_one_sentence_reports_its_metrics_once(tmp_path):
    async def go():
        inner = _FakeTTS()
        wrapper = AudioCachingTTS(
            inner, cacheable=lambda text: False, voice_key=_VOICE, cache=_cache(tmp_path)
        )
        reported = []
        wrapper.on("metrics_collected", reported.append)
        await _say(wrapper, "আপনার ব্যালেন্স ৫০ টাকা।")
        return inner.requests, reported

    requests, reported = asyncio.run(go())
    assert len(requests) == 1
    assert len(reported) == 1
