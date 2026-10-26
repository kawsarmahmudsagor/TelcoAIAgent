"""Reuses the synthesized audio of filler lines (app.agent.quick_reply).

A filler is spoken the moment the customer stops, so its time to first audio is
the latency they hear. The same few lines come back call after call, so their
audio is kept on disk (storage/audio_cache/quick_responses/: one WAV each, plus
index.json) and in memory, and a repeat plays at once with no TTS request.

Only filler lines are cached (AudioCachingTTS's `cacheable`): a reply sentence
carries the customer's balance, data left or a price, and a near match there
would say the wrong number. A near match between fillers is fine ("জি, একটু চেক
করছি।" for "জি, চেক করছি।"), but never across topics or digits: a data pack line
never stands in for a minute pack line (cache_entities).
"""

import difflib
import hashlib
import json
import logging
import re
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions, tts, utils

logger = logging.getLogger("agent.audio_cache")

# A near match must be at least this similar (difflib ratio, 0-1).
MIN_SIMILARITY = 0.82
# Lines longer than this are never fillers (quick_reply.FILLER_MAX_WORDS is 12).
MAX_WORDS = 14
# Enough for every template line in a few voices; new lines stop being saved after it.
MAX_ENTRIES = 400

_PUNCT_RE = re.compile(r"[।,.?!\-\"':;()\[\]–—]")
_DIGITS_RE = re.compile(r"\d+")  # Bangla digits too

# What a line is about: two lines that differ here are never swapped.
_TOPIC_PATTERNS = [
    ("data", re.compile(r"ডাটা|ডেটা|ইন্টারনেট|নেট|\bdata\b|\binternet\b", re.I)),
    ("voice", re.compile(r"মিনিট|টকটাইম|\bminutes?\b|\bvoice\b|\btalk", re.I)),
    ("sms", re.compile(r"এসএমএস|\bsms\b", re.I)),
    ("bundle", re.compile(r"কম্বো|বান্ডেল|\bcombo\b|\bbundle\b", re.I)),
    ("balance", re.compile(r"ব্যালেন্স|\bbalance\b", re.I)),
    ("usage", re.compile(r"ইউসেজ|খরচ|হিসাব|\busage\b", re.I)),
    ("recharge", re.compile(r"রিচার্জ|টপ\s*আপ|\brecharge\b|\btop\s*up\b", re.I)),
    ("offer", re.compile(r"অফার|\boffers?\b", re.I)),
    ("points", re.compile(r"পয়েন্ট|পয়েন্ট|রিওয়ার্ড|\bpoints?\b|\brewards?\b", re.I)),
    ("network", re.compile(r"নেটওয়ার্ক|নেটওয়ার্ক|সিগন্যাল|\bnetwork\b|\bsignal\b", re.I)),
    ("complaint", re.compile(r"অভিযোগ|সমস্যা|\bcomplaint\b|\bproblem\b|\bissue\b", re.I)),
    ("transactions", re.compile(r"লেনদেন|কাটা|কেটে|\btransactions?\b|\bdeduct", re.I)),
    ("pack", re.compile(r"প্যাক|প্যাকেজ|\bpacks?\b|\bpackages?\b", re.I)),
]


def normalize_text(text: str) -> str:
    """Lowercase, punctuation and extra spaces gone."""
    return " ".join(_PUNCT_RE.sub(" ", text).lower().split())


def cache_entities(text: str) -> list[str]:
    """The line's topics and digits: a near match must have the same ones."""
    found = [name for name, pattern in _TOPIC_PATTERNS if pattern.search(text)]
    found += [f"n{d}" for d in _DIGITS_RE.findall(text)]
    return sorted(found)


@dataclass
class CachedAudio:
    id: str
    text: str
    normalized_text: str
    file_name: str
    # Voice id and TTS model: a cached line only plays in the voice it was made in.
    voice_key: str
    sample_rate: int
    num_channels: int
    duration: float
    entities: list[str] = field(default_factory=list)
    use_count: int = 0
    created_at: float = 0.0
    pcm_data: bytes | None = None

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.pop("pcm_data", None)
        return out


class AudioCache:
    """The cached lines, on disk and in memory; shared by every session of the worker."""

    def __init__(self, storage_dir: Path | str | None = None) -> None:
        if storage_dir is None:
            storage_dir = (
                Path(__file__).resolve().parents[2] / "storage" / "audio_cache" / "quick_responses"
            )
        # Created on the first save: a worker that never says a filler leaves no trace.
        self.storage_dir = Path(storage_dir)
        self.index_path = self.storage_dir / "index.json"
        self._entries: list[CachedAudio] = []
        self._lock = threading.Lock()
        self._load()

    def __len__(self) -> int:
        return len(self._entries)

    def _load(self) -> None:
        if not self.index_path.exists():
            return
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("could not read the audio cache index: %s", exc)
            return
        for raw in data.get("entries", []):
            try:
                item = CachedAudio(**raw)
                item.pcm_data = _read_wav(self.storage_dir / item.file_name)
            except (OSError, TypeError, wave.Error) as exc:
                logger.warning("skipping cached audio %r: %s", raw.get("file_name"), exc)
                continue
            self._entries.append(item)
        logger.info("loaded %d cached filler lines from %s", len(self._entries), self.storage_dir)

    def _save_index(self) -> None:
        data = {"entries": [item.to_dict() for item in self._entries]}
        tmp = self.index_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.index_path)
        except OSError as exc:
            logger.warning("could not save the audio cache index: %s", exc)

    def find(
        self, text: str, voice_key: str, sample_rate: int, min_similarity: float = MIN_SIMILARITY
    ) -> tuple[CachedAudio, float] | None:
        """The cached line for `text`: the same words, else the most similar one
        above min_similarity with the same topics and digits. Same voice and
        sample rate only."""
        norm = normalize_text(text)
        if not norm:
            return None
        entities = cache_entities(text)
        with self._lock:
            candidates = [
                item
                for item in self._entries
                if item.voice_key == voice_key
                and item.sample_rate == sample_rate
                and item.entities == entities
            ]
        best: tuple[CachedAudio, float] | None = None
        for item in candidates:
            if item.normalized_text == norm:
                return item, 1.0
            ratio = difflib.SequenceMatcher(None, norm, item.normalized_text).ratio()
            if ratio >= min_similarity and (best is None or ratio > best[1]):
                best = (item, ratio)
        return best

    def has_line(self, text: str) -> bool:
        """Whether these exact words are cached, in any voice."""
        norm = normalize_text(text)
        with self._lock:
            return any(item.normalized_text == norm for item in self._entries)

    def record_hit(self, item: CachedAudio) -> None:
        # In memory only: written with the next save, not on every hit.
        item.use_count += 1

    def save(
        self, text: str, pcm_data: bytes, sample_rate: int, num_channels: int, voice_key: str
    ) -> CachedAudio | None:
        """Stores a line's audio; None when the cache is full."""
        norm = normalize_text(text)
        entities = cache_entities(text)
        item_id = hashlib.sha256(
            f"{voice_key}:{sample_rate}:{norm}".encode("utf-8")
        ).hexdigest()[:16]
        with self._lock:
            for existing in self._entries:
                if existing.id == item_id:
                    return existing
            if len(self._entries) >= MAX_ENTRIES:
                return None
            file_name = f"{item_id}.wav"
            try:
                self.storage_dir.mkdir(parents=True, exist_ok=True)
                duration = _write_wav(
                    self.storage_dir / file_name, pcm_data, sample_rate, num_channels
                )
            except (OSError, wave.Error) as exc:
                logger.warning("could not save cached audio for %r: %s", text, exc)
                return None
            item = CachedAudio(
                id=item_id,
                text=text,
                normalized_text=norm,
                file_name=file_name,
                voice_key=voice_key,
                sample_rate=sample_rate,
                num_channels=num_channels,
                duration=round(duration, 2),
                entities=entities,
                use_count=1,
                created_at=time.time(),
                pcm_data=pcm_data,
            )
            self._entries.append(item)
            self._save_index()
        logger.info("cached filler audio %r (%.2f s)", text, duration)
        return item


def _read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        return wf.readframes(wf.getnframes())


def _write_wav(path: Path, pcm_data: bytes, sample_rate: int, num_channels: int) -> float:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return len(pcm_data) / (sample_rate * num_channels * 2)


_CACHE: AudioCache | None = None


def get_audio_cache() -> AudioCache:
    """The worker's one cache, loaded on first use."""
    global _CACHE
    if _CACHE is None:
        _CACHE = AudioCache()
    return _CACHE


class _CachedStream(tts.ChunkedStream):
    """Plays a cached line's audio: no request, no wait."""

    def __init__(
        self,
        *,
        tts_instance: tts.TTS,
        input_text: str,
        item: CachedAudio,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts_instance, input_text=input_text, conn_options=conn_options)
        self._item = item

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=self._item.sample_rate,
            num_channels=self._item.num_channels,
            mime_type="audio/pcm",
        )
        output_emitter.push(self._item.pcm_data or b"")
        output_emitter.flush()


class _RecordingStream(tts.ChunkedStream):
    """The wrapped TTS's audio, passed through; a cacheable line's audio is
    saved once it is complete."""

    def __init__(
        self,
        *,
        tts_instance: "AudioCachingTTS",
        input_text: str,
        upstream: tts.ChunkedStream,
        record: bool,
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(tts=tts_instance, input_text=input_text, conn_options=conn_options)
        self._caching_tts = tts_instance
        self._upstream = upstream
        self._record = record

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=self._caching_tts.sample_rate,
            num_channels=self._caching_tts.num_channels,
            mime_type="audio/pcm",
        )
        captured = bytearray()
        async with self._upstream as upstream:
            async for audio in upstream:
                data = audio.frame.data.tobytes()
                if self._record:
                    captured.extend(data)
                output_emitter.push(data)
        output_emitter.flush()
        if self._record and captured:
            self._caching_tts.store(self._input_text, bytes(captured))


class AudioCachingTTS(tts.TTS):
    """Wraps a TTS: a cacheable line (a filler) plays from the cache when it is
    there, and is saved when it isn't. Everything else goes straight through."""

    def __init__(
        self,
        wrapped: tts.TTS,
        *,
        cacheable: Callable[[str], bool],
        voice_key: str,
        cache: AudioCache | None = None,
    ) -> None:
        super().__init__(
            capabilities=wrapped.capabilities,
            sample_rate=wrapped.sample_rate,
            num_channels=wrapped.num_channels,
        )
        self._wrapped = wrapped
        self._cacheable = cacheable
        self._voice_key = voice_key
        # Not `cache or ...`: an empty cache is falsy (__len__).
        self._cache = cache if cache is not None else get_audio_cache()
        # Metrics aren't forwarded: the wrapper's own stream (a ChunkedStream on
        # this TTS) already reports each sentence, so forwarding logged it twice.
        self._wrapped.on("error", self._forward_error)

    def _forward_error(self, *args, **kwargs) -> None:
        self.emit("error", *args, **kwargs)

    @property
    def model(self) -> str:
        return self._wrapped.model

    @property
    def provider(self) -> str:
        return self._wrapped.provider

    def prewarm(self) -> None:
        self._wrapped.prewarm()

    async def aclose(self) -> None:
        self._wrapped.off("error", self._forward_error)
        await self._wrapped.aclose()

    def _is_cacheable(self, text: str) -> bool:
        return 0 < len(text.split()) <= MAX_WORDS and self._cacheable(text)

    def store(self, text: str, pcm_data: bytes) -> None:
        self._cache.save(text, pcm_data, self.sample_rate, self.num_channels, self._voice_key)

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
        clean = text.strip()
        cacheable = self._is_cacheable(clean)
        if cacheable:
            match = self._cache.find(clean, self._voice_key, self.sample_rate)
            if match is not None:
                item, ratio = match
                self._cache.record_hit(item)
                logger.info("filler audio from cache: %r as %r (%.2f)", clean, item.text, ratio)
                return _CachedStream(
                    tts_instance=self, input_text=clean, item=item, conn_options=conn_options
                )
        return _RecordingStream(
            tts_instance=self,
            input_text=clean,
            upstream=self._wrapped.synthesize(text, conn_options=conn_options),
            record=cacheable,
            conn_options=conn_options,
        )
