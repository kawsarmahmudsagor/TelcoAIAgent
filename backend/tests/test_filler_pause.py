"""A pause after a template filler line: the reply waits 1 to 1.5 s after the
line even when it is ready, as a care agent checks before answering
(GatedAgent.tts_node adds silence after the line's audio)."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from livekit import rtc
from livekit.agents import Agent

from app.agent.gated_agent import GatedAgent
from app.agent.quick_reply import QuickReplyRuntime
from app.config import Settings
from app.services.agent_config_service import resolve

_LINE = "জি, আপনার ব্যালেন্সটা চেক করছি।"
_RATE = 24000


def _quick(llm_lines: bool) -> QuickReplyRuntime:
    settings = Settings(_env_file=None)
    config = resolve(None, settings)
    config.quick_reply_enabled = True
    config.quick_filler_llm = llm_lines
    quick = QuickReplyRuntime(config, settings, "k", httpx.AsyncClient())
    quick.said.append(_LINE)
    return quick


def _frame(ms: int) -> rtc.AudioFrame:
    samples = _RATE * ms // 1000
    return rtc.AudioFrame(b"\x01\x00" * samples, _RATE, 1, samples)


async def _speak(quick, text: str, monkeypatch) -> float:
    """Seconds of audio tts_node gives for `text` (TTS faked as 0.5 s)."""

    async def fake_tts(agent, chunks, model_settings):
        async for _ in chunks:
            pass
        yield _frame(500)

    monkeypatch.setattr(Agent.default, "tts_node", fake_tts)
    gate = SimpleNamespace(quick=quick)
    agent = SimpleNamespace(_gate=gate)

    async def text_stream():
        for part in text.split(" "):
            yield part + " "

    seconds = 0.0
    async for frame in GatedAgent.tts_node(agent, text_stream(), None):
        seconds += frame.samples_per_channel / frame.sample_rate
    return seconds


def test_a_template_filler_is_followed_by_a_pause(monkeypatch):
    seconds = asyncio.run(_speak(_quick(llm_lines=False), _LINE, monkeypatch))
    assert 0.5 + 1.0 <= seconds <= 0.5 + 1.5 + 0.01


def test_the_pause_varies(monkeypatch):
    lengths = {round(asyncio.run(_speak(_quick(False), _LINE, monkeypatch)), 2) for _ in range(8)}
    assert len(lengths) > 1


@pytest.mark.parametrize(
    ("llm_lines", "text"),
    [
        (True, _LINE),  # the model writes the lines: no pause
        (False, "৫০ টাকা আছে আপনার ব্যালেন্সে।"),  # the reply itself
    ],
)
def test_no_pause_otherwise(monkeypatch, llm_lines, text):
    assert asyncio.run(_speak(_quick(llm_lines), text, monkeypatch)) == pytest.approx(0.5)


def test_no_quick_replies_no_pause(monkeypatch):
    assert asyncio.run(_speak(None, _LINE, monkeypatch)) == pytest.approx(0.5)


def test_the_silence_matches_the_audio_format(monkeypatch):
    frames = []

    async def go():
        async def fake_tts(agent, chunks, model_settings):
            async for _ in chunks:
                pass
            yield rtc.AudioFrame(b"\x01\x00" * 4800, 48000, 2, 2400)

        monkeypatch.setattr(Agent.default, "tts_node", fake_tts)
        agent = SimpleNamespace(_gate=SimpleNamespace(quick=_quick(False)))

        async def one():
            yield _LINE

        async for frame in GatedAgent.tts_node(agent, one(), None):
            frames.append(frame)

    asyncio.run(go())
    assert all((f.sample_rate, f.num_channels) == (48000, 2) for f in frames)
    assert all(not any(f.data) for f in frames[1:])  # silence
