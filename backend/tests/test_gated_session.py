"""The voice turn gate's session wiring: what it does to the session for each
kind of speech. The AgentSession and room are fakes; the judge is a stub."""

import asyncio
import json
from types import SimpleNamespace

import numpy as np
import pytest
from livekit.agents import StopResponse, llm

from app.agent import entrypoint, gated_agent
from app.agent.gated_agent import (
    OTHER_LANGUAGE_LINE,
    USER_TURN_TOPIC,
    GateConfig,
    PauseConfig,
    TurnGateController,
)
from app.agent.turn_gate import Thresholds
from app.agent.turn_judge import Judgement
from app.config import Settings
from app.services import agent_config_service


class FakeAudioOutput:
    can_pause = True

    def __init__(self):
        self.calls: list[str] = []

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")


class FakeSession:
    def __init__(self):
        self.output = SimpleNamespace(audio=FakeAudioOutput())
        self.agent_state = "listening"
        self.user_state = "listening"
        self.current_speech = None
        self.history = SimpleNamespace(items=[])
        self.calls: list[tuple] = []
        self.handlers: dict[str, object] = {}
        # These tests start after the greeting (see test_greeting_guard).
        self.userdata = SimpleNamespace(greeting_done=True)

    def on(self, event, handler):
        self.handlers[event] = handler

    def interrupt(self, *, force=False):
        self.calls.append(("interrupt", force))
        fut = asyncio.get_running_loop().create_future()
        fut.set_result(None)
        return fut

    def clear_user_turn(self):
        self.calls.append(("clear_user_turn",))

    def generate_reply(self, **kwargs):
        self.calls.append(("generate_reply", kwargs.get("user_input")))

    def say(self, text, **kwargs):
        self.calls.append(("say", text, kwargs.get("add_to_chat_ctx")))


class FakeRoom:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.payloads: list[dict] = []
        self.local_participant = self

    async def send_text(self, text, *, topic):
        self.payloads.append(json.loads(text))
        self.sent.append((topic, json.loads(text)["text"]))


def _controller(
    scores: dict[str, float | None] | float | None = 0.8,
    bengali=True,
    pause: PauseConfig | None = None,
    clock=None,
):
    session, room = FakeSession(), FakeRoom()
    judged: list[tuple[str, str]] = []

    async def judge(text, bot_state, route=False):
        judged.append((text, bot_state))
        if isinstance(scores, dict):
            return Judgement(scores.get(text))
        return Judgement(scores)

    gate = TurnGateController(
        session=session,
        room=room,
        config=GateConfig(
            thresholds=Thresholds(),
            interrupt_p=0.5,
            interrupt_min_words=2,
            stt_writes_bengali=bengali,
            pause=pause,
        ),
        judge=judge,
        **({"clock": clock} if clock is not None else {}),
    )
    gate.attach()
    return gate, session, room, judged


def _msg(text: str, confidence: float = 0.9) -> llm.ChatMessage:
    return llm.ChatMessage(role="user", content=[text], transcript_confidence=confidence)


def _heard(gate: TurnGateController, text: str, final: bool = True) -> None:
    gate.on_user_input_transcribed(SimpleNamespace(transcript=text, is_final=final))


async def _settle(gate: TurnGateController) -> None:
    while gate._tasks:
        await asyncio.gather(*list(gate._tasks))


async def _complete(gate: TurnGateController, text: str, confidence: float = 0.9) -> bool:
    """True if the turn went through, False if it was dropped."""
    try:
        await gate.on_user_turn_completed(_msg(text, confidence))
    except StopResponse:
        return False
    return True


# ---- session config ----


def test_ungated_turn_handling_is_unchanged():
    assert entrypoint._turn_handling(False) == {"turn_detection": "vad"}


def test_batch_stt_waits_longer_before_closing_the_turn():
    settings = Settings(_env_file=None)
    config = agent_config_service.resolve(None)
    config.stt_tts_provider = "openrouter"
    delay = entrypoint._endpoint_min_delay(settings, config)
    assert delay == 2.0
    for gated in (False, True):
        handling = entrypoint._turn_handling(gated, delay)
        assert handling["endpointing"] == {"min_delay": 2.0, "max_delay": 3.0}


def test_streaming_stt_keeps_the_library_endpointing():
    settings = Settings(_env_file=None)
    config = agent_config_service.resolve(None)
    for provider in ("elevenlabs", "deepgram"):
        config.stt_tts_provider = provider
        assert entrypoint._endpoint_min_delay(settings, config) is None
    assert "endpointing" not in entrypoint._turn_handling(True, None)


def test_gated_turn_handling_hands_interruption_to_the_gate():
    handling = entrypoint._turn_handling(True)
    assert handling["interruption"] == {
        "enabled": False,
        "discard_audio_if_uninterruptible": False,
    }
    # the LLM must not start on a turn the gate may still drop
    assert handling["preemptive_generation"] == {"enabled": False}


def test_gate_key_only_when_enabled_and_keyed():
    config = agent_config_service.resolve(None)
    off = Settings(_env_file=None, turn_gate_enabled=False, openrouter_api_key="or-key")
    assert entrypoint._gate_api_key(off, config) == ""
    no_key = Settings(_env_file=None, turn_gate_enabled=True, openrouter_api_key="")
    if agent_config_service.embedding_api_key(config, no_key) == "":
        assert entrypoint._gate_api_key(no_key, config) == ""
    on = Settings(_env_file=None, turn_gate_enabled=True, openrouter_api_key="or-key")
    assert entrypoint._gate_api_key(on, config)


@pytest.mark.parametrize(
    ("provider", "expected"), [("elevenlabs", True), ("openrouter", True), ("deepgram", False)]
)
def test_only_bengali_capable_stt_gets_the_other_language_rule(provider, expected):
    config = gated_agent.gate_config(Settings(_env_file=None), provider)
    assert config.stt_writes_bengali is expected


# ---- bot listening: finished turns ----


def test_addressed_turn_is_accepted_and_shown():
    async def go():
        gate, session, room, _ = _controller(0.8)
        assert await _complete(gate, "আমার বাজেট ৫০ লাখ")
        assert room.sent == [(USER_TURN_TOPIC, "আমার বাজেট ৫০ লাখ")]
        assert session.calls == []

    asyncio.run(go())


@pytest.mark.parametrize(
    ("text", "p"),
    [
        ("তুমি কি চা খাবে?", 0.05),
        ("বাংলাদেশের ক্রিকেট টিম সম্পর্কে বলুন", 0.03),
        ("ওই যে বলছিলাম", 0.24),
    ],
)
def test_low_score_is_dropped_silently_without_touching_the_agent(text, p):
    async def go():
        gate, session, room, _ = _controller(p)
        session.current_speech = object()  # a reply playing is left alone
        assert not await _complete(gate, text)
        assert room.sent == []
        assert session.calls == []

    asyncio.run(go())


def test_filler_is_dropped_without_asking_the_judge():
    async def go():
        gate, _, _, judged = _controller(0.9)
        assert not await _complete(gate, "hmm")
        assert not await _complete(gate, "")
        assert judged == []

    asyncio.run(go())


def _said(session: FakeSession, role: str, text: str) -> None:
    session.history.items.append(llm.ChatMessage(role=role, content=[text]))


def test_a_hum_answering_the_agents_question_goes_through_without_the_judge():
    async def go():
        gate, session, room, judged = _controller(0.9)
        _said(session, "assistant", "এখন কথা বলা যাবে?")
        # A tool result after the question doesn't hide it.
        session.history.items.append(
            llm.FunctionCallOutput(
                call_id="c1", name="search_apartments", output="", is_error=False
            )
        )
        assert await _complete(gate, "হুম")
        assert judged == []
        assert (USER_TURN_TOPIC, "হুম") in room.sent

    asyncio.run(go())


def test_a_hum_after_a_statement_or_with_no_history_is_dropped():
    async def go():
        gate, session, _, judged = _controller(0.9)
        assert not await _complete(gate, "hmm")
        _said(session, "assistant", "এখন কথা বলা যাবে?")
        _said(session, "assistant", "আমাদের কাছে ৩টি অপশন আছে।")
        assert not await _complete(gate, "hmm")
        _said(session, "assistant", "কোনটা দেখবেন?")
        _said(session, "user", "দ্বিতীয়টা")
        assert not await _complete(gate, "hmm")
        assert judged == []

    asyncio.run(go())


def test_other_language_gets_the_fixed_line():
    async def go():
        gate, session, _, judged = _controller(0.9)
        assert not await _complete(gate, "कल सुबह हम बाज़ार चलेंगे।")
        assert ("say", OTHER_LANGUAGE_LINE, False) in session.calls
        assert judged == []

    asyncio.run(go())


def test_judge_failure_lets_the_turn_through():
    async def go():
        gate, _, room, _ = _controller(None)
        assert await _complete(gate, "Is parking included?")
        assert room.sent

    asyncio.run(go())


def test_judge_starts_on_the_final_transcript_and_is_reused():
    async def go():
        gate, _, _, judged = _controller(0.8)
        _heard(gate, "Is parking", final=False)
        _heard(gate, "Is parking included?")
        await asyncio.sleep(0)
        assert judged == [("Is parking included?", "listening")]
        assert await _complete(gate, "Is parking included?")
        assert len(judged) == 1

    asyncio.run(go())


# ---- bot busy: barge-in ----


def _speaking(gate, session, bot_said: str = "") -> None:
    session.agent_state = "speaking"
    gate.bot_reply_started()
    gate.bot_said(bot_said)


def test_bystander_while_bot_speaks_does_nothing():
    async def go():
        gate, session, room, _ = _controller(0.1)
        _speaking(gate, session)
        _heard(gate, "আম্মু, এটা তো অনেক দামি।")
        await _settle(gate)
        assert session.calls == []
        assert room.sent == []

    asyncio.run(go())


def test_a_sound_tag_while_bot_speaks_does_nothing():
    async def go():
        gate, session, room, judged = _controller(0.9)
        _speaking(gate, session)
        _heard(gate, "[clears throat]")
        await _settle(gate)
        assert session.calls == []
        assert room.sent == []
        assert judged == []

    asyncio.run(go())


def test_a_sound_tag_turn_is_dropped_without_asking_the_judge():
    async def go():
        gate, _, room, judged = _controller(0.9)
        assert not await _complete(gate, "[clears throat]")
        assert judged == []
        assert room.sent == []

    asyncio.run(go())


def test_own_voice_through_the_speakers_does_not_interrupt():
    async def go():
        gate, session, _, judged = _controller(0.9)
        _speaking(gate, session, "The Banani flat is 1,400 sqft with two bedrooms")
        _heard(gate, "the banani flat is fourteen hundred sqft with two bedrooms")
        await _settle(gate)
        assert session.calls == []
        assert judged == []

    asyncio.run(go())


def test_stop_phrase_while_still_talking_only_interrupts():
    async def go():
        gate, session, room, judged = _controller({"না না, বনানী": 0.8})
        _speaking(gate, session)
        session.user_state = "speaking"
        _heard(gate, "না না,", final=False)
        await _settle(gate)
        assert session.calls == [("interrupt", True)]
        assert judged == []
        # the library then delivers the whole sentence, which is judged as a whole
        session.agent_state = "listening"
        assert await _complete(gate, "না না, বনানী")
        assert room.sent == [(USER_TURN_TOPIC, "না না, বনানী")]
        assert judged == [("না না, বনানী", "listening")]

    asyncio.run(go())


def test_barge_in_on_a_fragment_is_dropped_when_the_whole_turn_is_off_topic():
    # Seen live: while the bot spoke, only "সম্পর্কে বলুন" was heard (0.71 without
    # context), so the gate interrupted; the whole turn asks about cricket.
    async def go():
        fragment = "সম্পর্কে বলুন"
        whole = "বাংলাদেশের ক্রিকেট টিম সম্পর্কে বলুন"
        gate, session, room, judged = _controller({fragment: 0.71, whole: 0.05})
        _speaking(gate, session)
        session.user_state = "speaking"
        _heard(gate, fragment)
        await _settle(gate)
        assert session.calls == [("interrupt", True)]
        session.agent_state = "listening"
        assert not await _complete(gate, whole)
        assert room.sent == []
        assert (whole, "listening") in judged

    asyncio.run(go())


def test_barge_in_turn_equal_to_what_was_judged_is_not_judged_again():
    async def go():
        heard = "What was the price of the Banani flat again?"
        gate, session, room, judged = _controller(0.7)
        _speaking(gate, session)
        session.user_state = "speaking"
        _heard(gate, heard)
        await _settle(gate)
        session.agent_state = "listening"
        assert await _complete(gate, heard)
        assert judged == [(heard, "speaking")]
        assert room.sent == [(USER_TURN_TOPIC, heard)]

    asyncio.run(go())


def test_addressed_barge_in_after_user_stopped_is_answered_by_the_gate():
    async def go():
        gate, session, room, _ = _controller(0.7)
        _speaking(gate, session)
        _heard(gate, "Hold on, what was the price again?")
        await _settle(gate)
        assert session.calls == [
            ("interrupt", True),
            ("clear_user_turn",),
            ("generate_reply", "Hold on, what was the price again?"),
        ]
        assert room.sent == [(USER_TURN_TOPIC, "Hold on, what was the price again?")]
        # if the library still commits the same speech, it isn't answered twice
        assert not await _complete(gate, "hold on what was the price again")

    asyncio.run(go())


def test_one_word_barge_in_does_not_interrupt():
    async def go():
        gate, session, _, _ = _controller(0.9)
        _speaking(gate, session)
        _heard(gate, "okay")
        await _settle(gate)
        assert session.calls == []

    asyncio.run(go())


def test_short_answer_while_thinking_is_queued_not_lost():
    async def go():
        gate, session, room, _ = _controller(0.8)
        session.agent_state = "thinking"
        _heard(gate, "হ্যাঁ")
        await _settle(gate)
        assert session.calls == [("generate_reply", "হ্যাঁ")]
        assert room.sent == [(USER_TURN_TOPIC, "হ্যাঁ")]

    asyncio.run(go())


def test_gate_reports_the_turns_it_answers_itself():
    async def go():
        gate, session, _, _ = _controller(0.8)
        replies: list[str] = []
        gate.on_gate_reply = replies.append
        session.agent_state = "thinking"
        _heard(gate, "হ্যাঁ")
        await _settle(gate)
        assert replies == ["হ্যাঁ"]

    asyncio.run(go())


def test_interim_transcripts_never_reach_the_judge():
    async def go():
        gate, session, _, judged = _controller(0.9)
        _speaking(gate, session)
        _heard(gate, "what was the", final=False)
        await _settle(gate)
        assert judged == []
        assert session.calls == []

    asyncio.run(go())


# ---- bot speaking: pause on loud speech ----


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


_PAUSE = PauseConfig(
    min_speech_s=0.3, margin_db=8.0, fallback_dbfs=-35.0, resume_after_s=3.0, max_pause_s=8.0
)


def _paused(scores=0.8):
    clock = FakeClock()
    gate, session, room, judged = _controller(scores, pause=_PAUSE, clock=clock)
    return gate, session, room, judged, clock


def _frames(gate, clock, db: float, seconds: float) -> None:
    """Mic frames of 10 ms at `db`."""
    for _ in range(round(seconds / 0.01)):
        clock.now += 0.01
        gate.on_audio_level(db, 0.01)


def _talking_over_bot(gate, session) -> None:
    _speaking(gate, session)
    session.user_state = "speaking"


def test_loud_speech_over_the_bot_pauses_it():
    gate, session, _, _, clock = _paused()
    _talking_over_bot(gate, session)
    _frames(gate, clock, -20.0, 0.25)
    assert session.output.audio.calls == []
    _frames(gate, clock, -20.0, 0.1)
    assert session.output.audio.calls == ["pause"]
    _frames(gate, clock, -20.0, 0.5)
    assert session.output.audio.calls == ["pause"]


def test_quiet_speech_over_the_bot_does_not_pause_it():
    gate, session, _, _, clock = _paused()
    _talking_over_bot(gate, session)
    _frames(gate, clock, -45.0, 2.0)
    assert session.output.audio.calls == []


def test_loud_sound_the_vad_does_not_call_speech_does_not_pause():
    gate, session, _, _, clock = _paused()
    _speaking(gate, session)  # user_state stays "listening"
    _frames(gate, clock, -10.0, 1.0)
    assert session.output.audio.calls == []


def test_no_pause_while_the_bot_is_listening():
    gate, session, _, _, clock = _paused()
    session.user_state = "speaking"
    _frames(gate, clock, -10.0, 1.0)
    assert session.output.audio.calls == []


def test_no_pause_during_the_greeting():
    gate, session, _, _, clock = _paused()
    session.userdata.greeting_done = False
    _talking_over_bot(gate, session)
    _frames(gate, clock, -10.0, 1.0)
    assert session.output.audio.calls == []


def test_no_pause_without_the_pause_config():
    clock = FakeClock()
    gate, session, _, _ = _controller(clock=clock)
    _talking_over_bot(gate, session)
    _frames(gate, clock, -10.0, 1.0)
    assert session.output.audio.calls == []


async def _calibrate(gate, session, clock, db: float, text: str = "Banani te flat ache?") -> bool:
    """A turn spoken at `db` while the bot listens; True if the gate accepted it."""
    session.agent_state = "listening"
    gate._on_agent_state_changed(SimpleNamespace(new_state="listening"))
    session.user_state = "speaking"
    _frames(gate, clock, db, 1.0)
    session.user_state = "listening"
    return await _complete(gate, text)


def test_the_bar_follows_the_callers_own_level():
    # -32 dBFS clears the -35 fallback, but not a caller who talks at -20 (bar -28).
    async def go():
        gate, session, _, _, clock = _paused()
        assert await _calibrate(gate, session, clock, -20.0)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -32.0, 1.0)
        assert session.output.audio.calls == []
        _frames(gate, clock, -25.0, 0.4)
        assert session.output.audio.calls == ["pause"]

    asyncio.run(go())


def test_a_quiet_caller_lowers_the_bar():
    async def go():
        gate, session, _, _, clock = _paused()
        assert await _calibrate(gate, session, clock, -40.0)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -45.0, 0.4)
        assert session.output.audio.calls == ["pause"]

    asyncio.run(go())


def test_a_dropped_turn_does_not_calibrate():
    async def go():
        gate, session, _, _, clock = _paused(scores=0.1)
        # A loud bystander, dropped by the judge.
        assert not await _calibrate(gate, session, clock, -10.0, "আম্মু, এটা তো অনেক দামি।")
        _talking_over_bot(gate, session)
        _frames(gate, clock, -30.0, 0.4)  # clears the fallback bar
        assert session.output.audio.calls == ["pause"]

    asyncio.run(go())


def test_paused_bot_resumes_when_the_judge_rejects_the_speech():
    async def go():
        gate, session, _, _, clock = _paused(scores=0.1)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        _heard(gate, "আম্মু, এটা তো অনেক দামি।")
        await _settle(gate)
        assert session.output.audio.calls == ["pause", "resume"]
        assert session.calls == []

    asyncio.run(go())


def test_after_a_rejection_the_same_speech_does_not_pause_again():
    async def go():
        gate, session, _, _, clock = _paused(scores=0.1)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        _heard(gate, "আম্মু, এটা তো অনেক দামি।")
        await _settle(gate)
        _frames(gate, clock, -20.0, 1.0)
        assert session.output.audio.calls == ["pause", "resume"]
        session.user_state = "listening"
        _frames(gate, clock, -60.0, 0.1)
        session.user_state = "speaking"
        _frames(gate, clock, -20.0, 0.4)
        assert session.output.audio.calls == ["pause", "resume", "pause"]

    asyncio.run(go())


def test_paused_bot_resumes_on_its_own_echo():
    async def go():
        bot = "Banani te amader tinti flat ache, shobcheye kom daam pochattor lakh."
        gate, session, _, _, clock = _paused()
        _speaking(gate, session, bot)
        session.user_state = "speaking"
        _frames(gate, clock, -20.0, 0.4)
        _heard(gate, "amader tinti flat ache shobcheye kom daam")
        await _settle(gate)
        assert session.output.audio.calls == ["pause", "resume"]

    asyncio.run(go())


def test_paused_bot_is_interrupted_when_the_judge_accepts():
    async def go():
        gate, session, _, _, clock = _paused(scores=0.9)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        session.user_state = "listening"
        _heard(gate, "What about Gulshan instead?")
        await _settle(gate)
        assert session.calls[0] == ("interrupt", True)
        # Released after the interrupt, or the next reply would play into a paused output.
        assert session.output.audio.calls == ["pause", "resume"]

    asyncio.run(go())


def test_interim_transcripts_keep_the_bot_paused():
    async def go():
        gate, session, _, _, clock = _paused()
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        _heard(gate, "what about", final=False)
        await _settle(gate)
        assert session.output.audio.calls == ["pause"]

    asyncio.run(go())


def test_paused_bot_resumes_after_the_caller_goes_quiet_with_no_decision():
    gate, session, _, _, clock = _paused()
    _talking_over_bot(gate, session)
    _frames(gate, clock, -20.0, 0.4)
    session.user_state = "listening"
    _frames(gate, clock, -60.0, 2.9)
    assert session.output.audio.calls == ["pause"]
    _frames(gate, clock, -60.0, 0.2)
    assert session.output.audio.calls == ["pause", "resume"]


def test_a_pause_never_outlasts_the_maximum():
    gate, session, _, _, clock = _paused()
    _talking_over_bot(gate, session)
    _frames(gate, clock, -20.0, 7.0)
    assert session.output.audio.calls == ["pause"]
    _frames(gate, clock, -20.0, 1.5)
    assert session.output.audio.calls == ["pause", "resume"]


def test_pause_is_released_when_the_bot_stops_speaking():
    gate, session, _, _, clock = _paused()
    _talking_over_bot(gate, session)
    _frames(gate, clock, -20.0, 0.4)
    session.agent_state = "listening"
    gate._on_agent_state_changed(SimpleNamespace(new_state="listening"))
    assert session.output.audio.calls == ["pause", "resume"]


def test_release_pause_is_a_no_op_when_not_paused():
    gate, session, _, _, _ = _paused()
    gate.release_pause()
    assert session.output.audio.calls == []


def test_the_agent_meters_the_mic_audio_it_passes_to_the_stt():
    from livekit import rtc

    async def go():
        gate, _, _, _ = _controller()
        levels: list[tuple[float, float]] = []
        gate.on_audio_level = lambda db, s: levels.append((round(db), s))
        agent = gated_agent.GatedAgent(gate=gate, instructions="")
        samples = (np.full(480, 3277, dtype=np.int16)).tobytes()  # a tenth of full scale
        frame = rtc.AudioFrame(samples, sample_rate=48000, num_channels=1, samples_per_channel=480)

        async def mic():
            yield frame

        out = [f async for f in agent._metered(mic())]
        assert out == [frame]
        assert levels == [(-20, 0.01)]

    asyncio.run(go())


# ---- speech over the agent: the pause as evidence, nothing lost ----

# run_47, +148 s: a real question over the agent that Jev scored 0.43.
_MIRPUR = "মিরপুর বারোতে আমি যদি buy করতে চাই কোন flat তাহলে কি কোন option আছে?"


def test_a_question_that_paused_the_bot_interrupts_it_on_a_modest_score():
    async def go():
        gate, session, room, _, clock = _paused(scores=0.43)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        session.user_state = "listening"
        _heard(gate, _MIRPUR)
        await _settle(gate)
        assert session.calls == [
            ("interrupt", True),
            ("clear_user_turn",),
            ("generate_reply", _MIRPUR),
        ]
        assert room.sent == [(USER_TURN_TOPIC, _MIRPUR)]

    asyncio.run(go())


def test_the_pause_still_counts_after_it_let_go_before_the_transcript():
    async def go():
        gate, session, _, _, clock = _paused(scores=0.43)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        session.user_state = "listening"
        # STT + judge took longer than resume_after_s (run_47: 3.05 s).
        _frames(gate, clock, -60.0, 3.2)
        assert session.output.audio.calls == ["pause", "resume"]
        _heard(gate, _MIRPUR)
        await _settle(gate)
        assert session.calls[0] == ("interrupt", True)

    asyncio.run(go())


def test_a_paused_bot_still_resumes_for_a_bystander():
    async def go():
        gate, session, _, _, clock = _paused(scores=0.1)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        session.user_state = "listening"
        _heard(gate, "আম্মু, এটা তো অনেক দামি।")
        await _settle(gate)
        assert session.calls == []

    asyncio.run(go())


def test_speech_that_did_not_pause_the_bot_is_dropped_below_the_interrupt_bar():
    # run_54: someone nearby, quieter than the customer, scored 0.45 and was
    # queued and answered.
    async def go():
        line = "তার একটা কনসেপ্ট হবে ভ্যালিড এবং আমি যদি সেখানে বলতে চাই সেটা হলো যে ভাই দেখেন"
        gate, session, room, _, _ = _paused(scores=0.45)
        _speaking(gate, session)  # no loud frames: the pause never fired
        _heard(gate, line)
        await _settle(gate)
        assert session.calls == []
        assert room.sent == []

    asyncio.run(go())


def test_the_pause_evidence_ends_with_the_reply_it_paused():
    async def go():
        gate, session, _, _, clock = _paused(scores=0.43)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        session.agent_state = "listening"
        gate._on_agent_state_changed(SimpleNamespace(new_state="listening"))
        session.user_state = "listening"
        _speaking(gate, session)
        _heard(gate, _MIRPUR)
        await _settle(gate)
        # Judged against the full interrupt bar again: below it, dropped.
        assert session.calls == []

    asyncio.run(go())


def test_the_pause_evidence_is_used_once():
    async def go():
        gate, session, _, _, clock = _paused(scores={"আম্মু, এটা তো অনেক দামি।": 0.1, _MIRPUR: 0.43})
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        session.user_state = "listening"
        _heard(gate, "আম্মু, এটা তো অনেক দামি।")
        await _settle(gate)
        gate._buffer.clear()
        _heard(gate, _MIRPUR)
        await _settle(gate)
        assert session.calls == []

    asyncio.run(go())


def test_barge_in_steps_are_reported():
    async def go():
        gate, session, _, _, clock = _paused(scores=0.43)
        notes: list[str] = []
        gate.on_barge_in = notes.append
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        session.user_state = "listening"
        _heard(gate, _MIRPUR)
        await _settle(gate)
        assert notes[0].startswith("paused the agent: voice at the caller's level")
        assert notes[-1] == "interrupted the agent to answer the caller"

    asyncio.run(go())


def test_a_rejection_reports_its_score():
    async def go():
        gate, session, _, _, clock = _paused(scores=0.1)
        notes: list[str] = []
        gate.on_barge_in = notes.append
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        _heard(gate, "আম্মু, এটা তো অনেক দামি।")
        await _settle(gate)
        assert notes[-1] == "agent resumed (rejected, score 0.10)"

    asyncio.run(go())


# ---- noisy rooms: runs 52 and 53 ----


def test_a_rejected_line_does_not_join_later_noise():
    # run_52: a bystander (0.10), then "[background noise]", then a noise line
    # the judge gives 0.27 -- judged together they once got queued as a turn.
    async def go():
        bystander = "player আছে player আছে কথা বললে যে"
        noise = "We are before a full [static]"
        gate, session, room, judged = _controller({bystander: 0.10, noise: 0.27})
        _speaking(gate, session)
        _heard(gate, bystander)
        await _settle(gate)
        _heard(gate, "[background noise]")
        await _settle(gate)
        _heard(gate, noise)
        await _settle(gate)
        assert session.calls == []
        assert room.sent == []
        assert [text for text, _ in judged] == [bystander, noise]

    asyncio.run(go())


def test_someone_as_loud_as_the_customer_does_not_interrupt():
    # run_53: people nearby paused the agent (-22 to -34 dBFS) and scored 0.25-0.30.
    async def go():
        line = "সেটা তো আমরা এখানে সব discussion করতে পারি"
        gate, session, room, _, clock = _paused(scores=0.29)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        session.user_state = "listening"
        _heard(gate, line)
        await _settle(gate)
        assert session.calls == []
        assert room.sent == []
        assert session.output.audio.calls == ["pause", "resume"]

    asyncio.run(go())


def test_another_language_over_the_bot_never_interrupts():
    # run_53: Hindi among English words scored 0.51 and cut the agent off.
    async def go():
        gate, session, _, judged, clock = _paused(scores=0.9)
        _talking_over_bot(gate, session)
        _frames(gate, clock, -20.0, 0.4)
        _heard(gate, "आ वो लोग milestone repeat की")
        await _settle(gate)
        assert session.calls == []
        assert judged == []
        assert session.output.audio.calls == ["pause", "resume"]

    asyncio.run(go())


def test_sound_tags_never_reach_the_agent_or_the_screen():
    async def go():
        said = "হ্যাঁ, আমি কালকে আসছি। [গলা ঝারার শব্দ]"
        gate, session, room, _ = _controller(0.69)
        _speaking(gate, session)
        _heard(gate, said)
        await _settle(gate)
        assert ("generate_reply", "হ্যাঁ, আমি কালকে আসছি।") in session.calls
        assert room.sent == [(USER_TURN_TOPIC, "হ্যাঁ, আমি কালকে আসছি।")]

    asyncio.run(go())


def test_sound_tags_are_stripped_from_an_accepted_turn():
    async def go():
        gate, session, room, _ = _controller(0.9)
        message = _msg("[clears throat] আমার বাজেট ৫০ লাখ")
        try:
            await gate.on_user_turn_completed(message)
        except StopResponse:
            pass
        assert message.text_content == "আমার বাজেট ৫০ লাখ"
        assert room.sent == [(USER_TURN_TOPIC, "আমার বাজেট ৫০ লাখ")]

    asyncio.run(go())


def test_a_spoken_phone_number_reaches_the_agent_as_digits():
    # The LLM miscounts "double"/"triple" when it writes the digits itself.
    async def go():
        gate, session, room, _ = _controller(0.9)
        message = _msg("আমার নাম্বার zero one seven zero one double zero one three nine eight")
        try:
            await gate.on_user_turn_completed(message)
        except StopResponse:
            pass
        assert message.text_content == "আমার নাম্বার 01701001398"
        assert room.sent == [(USER_TURN_TOPIC, "আমার নাম্বার 01701001398")]

    asyncio.run(go())
