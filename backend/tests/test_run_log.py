import re
from types import SimpleNamespace

from livekit.agents.metrics import EOUMetrics, LLMMetrics, TTSMetrics

from app.agent.run_log import RunLog


class _Clock:
    def __init__(self, t: float = 1_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def _ev(at, **kw):
    return SimpleNamespace(created_at=at, **kw)


def _metrics(m):
    return SimpleNamespace(metrics=m)


def _llm(ttft, duration):
    return LLMMetrics(
        label="google", request_id="r", timestamp=0, duration=duration, ttft=ttft,
        cancelled=False, completion_tokens=20, prompt_tokens=900, prompt_cached_tokens=0,
        total_tokens=920, tokens_per_second=40.0,
    )


def _message(role, text, metrics=None):
    return SimpleNamespace(
        item=SimpleNamespace(
            type="message", role=role, text_content=text, interrupted=False,
            metrics=metrics or {},
        )
    )


def test_files_are_numbered_after_the_highest_run(tmp_path):
    (tmp_path / "run_1.log").write_text("")
    (tmp_path / "run_7.log").write_text("")
    log = RunLog.open("room-1", tmp_path)
    log.close()
    assert log.run_no == 8
    assert (tmp_path / "run_8.log").read_text(encoding="utf-8").startswith("Run 8 -- session room-1")


def test_a_turn_logs_every_part_and_a_summary(tmp_path):
    clock = _Clock()
    file = open(tmp_path / "run_1.log", "x", encoding="utf-8")
    log = RunLog("room-1", 1, file, clock=clock)

    # The greeting closes turn 0.
    log._on_item(_message("assistant", "Hello!"))

    log._on_user_state(_ev(1001.0, old_state="listening", new_state="speaking"))
    log._on_user_state(_ev(1003.0, old_state="speaking", new_state="listening"))
    log._on_transcribed(_ev(1003.2, is_final=True, transcript="2 bed in Uttara?", language="en"))
    log.judged("2 bed in Uttara?", "listening", 0.41, 0.93)
    log._on_metrics(_metrics(EOUMetrics(
        timestamp=0, end_of_utterance_delay=0.5, transcription_delay=0.2,
        on_user_turn_completed_delay=0.3,
    )))
    log._on_item(_message("user", "2 bed in Uttara?"))
    log._on_agent_state(_ev(1003.6, old_state="listening", new_state="thinking"))
    log._on_metrics(_metrics(_llm(0.6, 0.8)))
    call = SimpleNamespace(call_id="c1", name="search_apartments", arguments='{"area": "Uttara"}')
    log._on_tool(_ev(1004.4, update=SimpleNamespace(type="tool_call_started", function_call=call)))
    log._on_tool(_ev(1005.25, update=SimpleNamespace(type="tool_call_ended", call_id="c1", status="done")))
    log._on_metrics(_metrics(_llm(0.5, 1.1)))
    log._on_metrics(_metrics(TTSMetrics(
        label="elevenlabs", request_id="t", timestamp=0, ttfb=0.3, duration=0.9,
        audio_duration=4.0, cancelled=False, characters_count=60, streamed=False,
    )))
    log._on_agent_state(_ev(1006.9, old_state="thinking", new_state="speaking"))
    log._on_item(_message("assistant", "I found two.", {"e2e_latency": 3.9}))
    clock.t = 1010.0
    log._on_close(None)

    text = (tmp_path / "run_1.log").read_text(encoding="utf-8")
    assert "=== Turn 0: Greeting" in text
    assert "=== Turn 1: Caller speaks, agent replies" in text
    assert "[+   3.00 s]  Caller          stopped talking" in text
    assert "Jev             checked in 0.41 s: score 0.93 out of 1" in text
    assert "Tool            search_apartments finished after 0.85 s" in text
    # Dot leaders collapsed to ":" so the checks don't depend on label widths.
    summary = re.sub(r" \.+ ", " : ", " ".join(text.split("Turn 1 timing")[1].split()))
    assert "Jev relevance check : 0.41 s (1 check, score 0.93)" in summary
    assert "AI model (LLM) : 1.90 s in 2 calls [0.80 s, 1.10 s]" in summary
    assert "Tool: search_apartments : 0.85 s" in summary
    assert "Text-to-speech : 0.90 s for 4.0 s of speech" in summary
    assert "Preparing the reply : 3.30 s" in summary
    assert "TOTAL RESPONSE TIME : 3.90 s" in summary
    assert "Average response time : 3.90 s" in summary
    assert "=== Turn 2" not in text


def test_a_turn_the_gate_answers_is_not_called_typed(tmp_path):
    file = open(tmp_path / "run_1.log", "x", encoding="utf-8")
    log = RunLog("room-1", 1, file, clock=_Clock())
    log._on_item(_message("assistant", "Hello!"))

    # Queued behind the current reply: the gate reports it before the library
    # adds the user message, with no end-of-turn metrics.
    log.gate_reply("What about Uttara?")
    log._on_item(_message("user", "What about Uttara?"))
    log._on_agent_state(_ev(1001.0, old_state="listening", new_state="thinking"))
    log._on_agent_state(_ev(1002.5, old_state="thinking", new_state="speaking"))
    log._on_item(_message("assistant", "Four flats."))
    log._on_close(None)

    text = (tmp_path / "run_1.log").read_text(encoding="utf-8")
    assert 'Caller          said "What about Uttara?" (spoken while the agent was busy' in text
    assert "typed" not in text.split("=== Turn 1")[1]
    summary = re.sub(r" \.+ ", " : ", " ".join(text.split("Turn 1 timing")[1].split()))
    assert "TOTAL RESPONSE TIME : 1.50 s (turn gate let it through" in summary
    assert "Speech-to-text" not in summary


def test_a_typed_turn_is_still_typed(tmp_path):
    file = open(tmp_path / "run_1.log", "x", encoding="utf-8")
    log = RunLog("room-1", 1, file, clock=_Clock())
    log._on_item(_message("assistant", "Hello!"))
    log.gate_reply("something else")
    log._on_item(_message("user", "Uttara?"))
    log._on_close(None)
    assert 'Caller          typed "Uttara?"' in (tmp_path / "run_1.log").read_text(encoding="utf-8")


def test_router_lines_and_summary(tmp_path):
    file = open(tmp_path / "run_1.log", "x", encoding="utf-8")
    log = RunLog("room-1", 1, file, clock=_Clock())
    log._on_item(_message("assistant", "Hello!"))
    lookup = SimpleNamespace(name="search_apartments", args={"location": "Uttara"}, seconds=0.02)
    log.routed("listings", 0.98, [lookup], 0.65)
    log._on_item(_message("user", "What about Uttara?"))
    log._on_item(_message("assistant", "Four flats."))
    log._on_close(None)

    text = (tmp_path / "run_1.log").read_text(encoding="utf-8")
    assert 'Tool            search_apartments prefetched with location="Uttara"' in text
    assert "Router          Jev chose listings (0.98); ran search_apartments in 0.65 s" in text
    summary = re.sub(r" \.+ ", " : ", " ".join(text.split("Turn 1 timing")[1].split()))
    assert "Router : listings (0.98), ran search_apartments, 0.65 s" in summary
    assert "Tool: search_apartments (prefetched) 0.02 s" in summary


def test_quick_reply_lines_and_summary(tmp_path):
    file = open(tmp_path / "run_1.log", "x", encoding="utf-8")
    log = RunLog("room-1", 1, file, clock=_Clock())
    log._on_item(_message("assistant", "Hello!"))
    log.filler("Let me find those for you.", 0.9, 0.4)
    log._on_item(_message("user", "Flats in Uttara?"))
    log._on_item(_message("assistant", "Four flats."))
    log.fast_route(handed_off=False)
    log._on_item(_message("user", "Thanks!"))
    log._on_item(_message("assistant", "You're welcome."))
    log._on_close(None)

    text = (tmp_path / "run_1.log").read_text(encoding="utf-8")
    assert 'filler "Let me find those for you." queued 0.90 s after the caller stopped' in text
    turn1 = re.sub(r" \.+ ", " : ", " ".join(text.split("Turn 1 timing")[1].split("Turn 2")[0].split()))
    assert 'Quick reply filler : "Let me find those for you.", started 0.90 s after' in turn1
    assert "turn gate waited 0.40 s" in turn1
    turn2 = re.sub(r" \.+ ", " : ", " ".join(text.split("Turn 2 timing")[1].split()))
    assert "Quick reply answer : small model answered" in turn2


def test_barge_in_lines(tmp_path):
    file = open(tmp_path / "run_1.log", "x", encoding="utf-8")
    log = RunLog("room-1", 1, file, clock=_Clock())
    log._on_item(_message("assistant", "Hello!"))
    log.barge_in("paused the agent: voice at the caller's level (-22 dBFS)")
    log.barge_in("agent resumed (rejected, score 0.10)")
    log._on_close(None)

    text = (tmp_path / "run_1.log").read_text(encoding="utf-8")
    assert "Barge-in          speech over the agent" in text
    assert re.search(r"Barge-in\s+paused the agent: voice at the caller's level", text)
    assert re.search(r"Barge-in\s+agent resumed \(rejected, score 0\.10\)", text)
