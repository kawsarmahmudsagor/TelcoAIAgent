"""Per-session timing log, written for people to read: where every second of
each turn went.

One file per session, logs/run_<N>.log at the repo root (RUN_LOG_DIR overrides),
N one higher than the highest run there. The file opens with a short legend,
then groups lines by turn: each line is the clock time, seconds since the call
started, the part of the pipeline, and what happened in plain words. Every
agent reply ends with a timing summary of its turn, and the file ends with a
summary of the call.

The parts timed:
- speech-to-text: the caller stops talking -> their words arrive as text
- turn end: the caller stops talking -> the agent decides they've finished
- Jev: each relevance check of the turn gate (gated sessions only)
- AI model (LLM): each call; a reply that uses a tool takes two calls
- tools: each tool's run time (its database / API work)
- text-to-speech: time to first audio and synthesis time per sentence
- preparing the reply: the agent starts thinking -> starts speaking
- total response time: the caller stops talking -> the agent starts speaking

Lines also go to the "agent.timing" logger, so they show in the worker console.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TextIO

from livekit.agents import AgentSession
from livekit.agents.metrics import EOUMetrics, LLMMetrics, STTMetrics, TTSMetrics

logger = logging.getLogger("agent.timing")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUN_FILE = re.compile(r"^run_(\d+)\.log$")
_MAX_TEXT = 120
_PART_WIDTH = 15
_LABEL_WIDTH = 30

_LEGEND = """\
How to read this file
  Each line: clock time | seconds since the call started | part | what happened.
  Lines are grouped by turn. Turn 0 is the agent's greeting; every turn after
  that is one thing the caller said and the agent's reply to it. Each reply ends
  with a timing summary of its turn; the call summary is at the bottom.

  Speech-to-text    turns the caller's voice into text
  Turn end          waits after the caller goes quiet, to be sure they've finished
  Jev               checks the caller is talking to the agent, not someone else
                    (score 0 to 1; higher = addressed to the agent)
  Barge-in          speech over the agent: paused, resumed, interrupted or queued
  Router            runs the lookup a turn needs (a search) before the AI model,
                    so the model answers in one call instead of two
  Quick reply       the small model: asked for a filler line or a fast answer,
                    what it wrote or said, or why it was dropped or timed out
  AI model          the LLM writing the reply (a tool call needs a second call)
  Tool              the agent looking something up (database / API)
  Text-to-speech    turns the reply into voice
  Total response    caller stops talking -> agent starts speaking
"""

_AGENT_STATES = {
    "thinking": "is working on the reply",
    "speaking": "started speaking",
    "listening": "is listening",
    "initializing": "is starting up",
    "idle": "is idle",
}


def default_dir() -> Path:
    return _REPO_ROOT / "logs"


def _next_run_file(log_dir: Path) -> tuple[int, TextIO]:
    log_dir.mkdir(parents=True, exist_ok=True)
    taken = [int(m.group(1)) for p in log_dir.iterdir() if (m := _RUN_FILE.match(p.name))]
    n = max(taken, default=0) + 1
    while True:
        try:
            # "x": two sessions starting at once can't both claim the same number.
            return n, open(log_dir / f"run_{n}.log", "x", encoding="utf-8", buffering=1)
        except FileExistsError:
            n += 1


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _MAX_TEXT else text[: _MAX_TEXT - 3] + "..."


def _s(seconds: float | None) -> str:
    return "n/a" if seconds is None else f"{seconds:.2f} s"


def _duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} min {secs} s" if minutes else f"{secs} s"


def _wall_time(ts: float | None) -> str:
    if ts is None:
        return "n/a"
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3]


def _row(label: str, value: str) -> str:
    return f"    {(label + ' ').ljust(_LABEL_WIDTH, '.')} {value}"


@dataclass
class _Turn:
    index: int
    user_text: str | None = None
    typed: bool = False
    # Spoken while the agent was busy and answered by the turn gate itself.
    gate_reply: bool = False
    heard: bool = False
    user_started_at: float | None = None
    user_stopped_at: float | None = None
    thinking_at: float | None = None
    speaking_at: float | None = None
    turn_finished_at: float | None = None
    stt_delay: float | None = None
    # Caller stopped -> their first transcript, measured here: the library's
    # end-of-turn metrics (stt_delay) skip turns the gate drops or answers
    # itself, and a turn newer speech overtook.
    stt_heard_after: float | None = None
    stt_audio: float = 0.0
    eou_delay: float | None = None
    gate_delay: float | None = None
    jev: list[tuple[float, float | None]] = field(default_factory=list)
    jev_events: list[tuple[float, float, float | None]] = field(default_factory=list)
    # (Jev's lookup choice, its probability, tools run, seconds)
    router: tuple[str | None, float | None, list[str], float] | None = None
    router_event: tuple[float, float, str | None, float | None, list[str]] | None = None
    llm: list[tuple[float, float]] = field(default_factory=list)
    tools: list[tuple[str, float, str]] = field(default_factory=list)
    tool_events: list[tuple[float, float, str, str]] = field(default_factory=list)
    tts: list[tuple[float, float, float]] = field(default_factory=list)
    # Quick replies: the filler line (text, seconds after the caller stopped,
    # seconds the turn gate waited for it) and whether the small model answered.
    filler: tuple[str, float | None, float] | None = None
    filler_event: tuple[float, str, float | None, float] | None = None
    filler_text: str | None = None
    quick_speaking_at: float | None = None
    detail_speaking_at: float | None = None
    fast: str | None = None

    @property
    def empty(self) -> bool:
        return self.user_text is None and not (self.llm or self.tts or self.tools)


class RunLog:
    def __init__(self, label: str, run_no: int, file: TextIO, clock=time.time) -> None:
        self.label = label
        self.run_no = run_no
        self._file = file
        self._clock = clock
        self._started = clock()
        self._turn = _Turn(0)  # turn 0 is the greeting
        self._turn_count = 0
        self._heading_for: int | None = None
        self._tool_started: dict[str, tuple[str, float]] = {}
        # Turns the turn gate answered itself (gated_agent.on_gate_reply).
        self._gate_replies: list[str] = []
        self._responses: list[float] = []
        # The caller stopped and their words haven't come back from the STT yet.
        self._awaiting_text = False
        self._closed = False
        started = datetime.fromtimestamp(self._started)
        self._write(f"Run {run_no} -- session {label or '(unnamed)'}")
        self._write(f"Started {started.strftime('%A %d %B %Y, %H:%M:%S')}")
        self._write("")
        self._write(_LEGEND)

    @classmethod
    def open(cls, label: str, log_dir: Path | None = None) -> "RunLog":
        run_no, file = _next_run_file(log_dir or default_dir())
        logger.info("[%s] timing log: %s", label, file.name)
        return cls(label, run_no, file)

    def log_config(self, **items: str) -> None:
        """Active pipeline configuration (STT mode, TTS, LLM) shown at session start."""
        details = [f"  {k.upper()}: {v}" for k, v in items.items() if v]
        if details:
            self._write("Configuration:")
            for line in details:
                self._write(line)
            self._write("")

    def attach(self, session: AgentSession) -> None:
        session.on("user_state_changed", self._on_user_state)
        session.on("agent_state_changed", self._on_agent_state)
        session.on("user_input_transcribed", self._on_transcribed)
        session.on("metrics_collected", self._on_metrics)
        session.on("tool_execution_updated", self._on_tool)
        session.on("conversation_item_added", self._on_item)
        session.on("close", self._on_close)

    # ---- output ----

    def _write(self, line: str) -> None:
        if self._closed:
            return
        try:
            self._file.write(line + "\n")
        except Exception:
            logger.exception("could not write the timing log")
        if line.strip():
            try:
                logger.info("[%s] %s", self.label, line.rstrip())
            except Exception:
                pass

    def _event(self, part: str, text: str, at: float | None = None, heading: bool = True) -> None:
        if heading and self._heading_for != self._turn.index:
            self._heading_for = self._turn.index
            title = "Greeting" if self._turn.index == 0 else "Caller speaks, agent replies"
            self._write("")
            self._write(f"=== Turn {self._turn.index}: {title} ".ljust(72, "="))
        at = self._clock() if at is None else at
        wall = datetime.fromtimestamp(at).strftime("%H:%M:%S.%f")[:-3]
        self._write(f"{wall}  [+{at - self._started:7.2f} s]  {part:<{_PART_WIDTH}} {text}")

    # ---- events ----

    def _on_user_state(self, ev) -> None:
        if ev.new_state == "speaking":
            if self._turn.index > 0 and self._turn.empty:
                if self._turn.heard:
                    self._write("    (that speech was ignored: not addressed to the agent)")
                # Speech the gate dropped never became a turn; start over.
                self._turn = _Turn(self._turn.index)
            self._turn.user_started_at = ev.created_at
            self._awaiting_text = False
            self._event("Caller", "started talking", ev.created_at)
        elif ev.old_state == "speaking":
            # If the caller stopped, record their stop time.
            # Do NOT overwrite it if the agent is already preparing or speaking its reply.
            if self._turn.user_stopped_at is None or self._turn.speaking_at is None:
                self._turn.user_stopped_at = ev.created_at
            self._awaiting_text = True
            self._event("Caller", "stopped talking", ev.created_at)

    def _on_agent_state(self, ev) -> None:
        t = self._turn
        if ev.new_state == "thinking" and t.thinking_at is None:
            t.thinking_at = ev.created_at
        elif ev.new_state == "speaking":
            if t.speaking_at is None:
                t.speaking_at = ev.created_at
            stopped = t.user_stopped_at
            latency_str = f" ({_s(ev.created_at - stopped)} after caller stopped)" if stopped is not None and ev.created_at >= stopped else ""
            if t.filler_text and t.quick_speaking_at is None:
                t.quick_speaking_at = ev.created_at
                self._event(
                    "Agent",
                    f'started speaking quick response: "{_short(t.filler_text)}"{latency_str}',
                    ev.created_at,
                )
                return
            elif t.detail_speaking_at is None and t.index > 0:
                t.detail_speaking_at = ev.created_at
                self._event("Agent", f"started speaking detailed response{latency_str}", ev.created_at)
                return

        state = _AGENT_STATES.get(ev.new_state, f"is {ev.new_state}")
        self._event("Agent", state, ev.created_at)

    def _on_transcribed(self, ev) -> None:
        if ev.is_final:
            t = self._turn
            t.heard = True
            after = ""
            # Only the first final after the caller stops: a streaming STT's later
            # finals, or ones while they still talk, time nothing.
            if self._awaiting_text and t.user_stopped_at is not None:
                self._awaiting_text = False
                waited = ev.created_at - t.user_stopped_at
                if t.stt_heard_after is None:
                    t.stt_heard_after = waited
                after = f" {_s(waited)} after the caller stopped"
            lang = f" (language: {ev.language})" if getattr(ev, "language", None) else ""
            self._event(
                "Speech-to-text", f'heard "{_short(ev.transcript)}"{after}{lang}', ev.created_at
            )

    def judged(self, text: str, bot_state: str, seconds: float, p: float | None) -> None:
        """One Jev call of the turn gate (see gated_agent.jev_judge)."""
        self._turn.jev.append((seconds, p))
        self._turn.jev_events.append((self._clock() - seconds, seconds, p))
        if p is None:
            result = "no answer (failed or timed out), so the speech is accepted"
        else:
            result = f"score {p:.2f} out of 1"
        when = "" if bot_state == "listening" else f" (agent was {bot_state})"
        self._event("Jev", f"checked in {_s(seconds)}{when}: {result}")

    def routed(self, lookup: str | None, lookup_p: float | None, lookups, seconds: float) -> None:
        """The turn router's decision for a turn (see app.agent.prefetch): the
        lookups it ran before the AI model, if any."""
        choice = "no answer" if lookup is None else lookup
        if lookup_p is not None:
            choice += f" ({lookup_p:.2f})"
        for item in lookups:
            self._turn.tools.append((f"{item.name} (prefetched)", item.seconds, "done"))
            self._event(
                "Tool",
                f"{item.name} prefetched with {_args(json.dumps(item.args))}, "
                f"finished after {_s(item.seconds)}",
            )
        names = [item.name for item in lookups]
        self._turn.router = (lookup, lookup_p, names, seconds)
        self._turn.router_event = (self._clock() - seconds, seconds, lookup, lookup_p, names)
        if names:
            text = f"Jev chose {choice}; ran {', '.join(names)} in {_s(seconds)}"
        else:
            text = f"Jev chose {choice}; nothing prefetched ({_s(seconds)})"
        self._event("Router", text)

    def filler(self, text: str, started_after_s: float | None, waited_s: float) -> None:
        """A quick-reply filler line was queued (see gated_agent). It is spoken
        before the reply, so "Agent is speaking" below marks the filler's start;
        TOTAL RESPONSE TIME still times the reply."""
        self._turn.filler = (text, started_after_s, waited_s)
        self._turn.filler_text = text
        self._turn.filler_event = (self._clock(), text, started_after_s, waited_s)
        after = f" {_s(started_after_s)} after the caller stopped" if started_after_s is not None else ""
        self._event("Quick reply", f'filler "{_short(text)}" queued{after} (turn gate waited {_s(waited_s)})')

    def fast_route(self, handed_off: bool) -> None:
        """The small model took the turn; handed_off = it passed it on to the
        main model (the first AI model line is then the small model's)."""
        self._turn.fast = "handed off to the main model" if handed_off else "answered"
        self._event("Quick reply", f"small model {self._turn.fast}")

    def quick(self, what: str) -> None:
        """A step of the small model's work: a call made, its line or answer, a
        timeout or a dropped line (see quick_reply.QuickReplyRuntime.on_event)."""
        self._event("Quick reply", _short(what))

    def barge_in(self, what: str) -> None:
        """What the turn gate did with speech over the agent (see gated_agent):
        paused it, let it resume (and why), interrupted it or queued an answer."""
        self._event("Barge-in", what)

    def gate_reply(self, text: str) -> None:
        """The turn gate is answering `text` itself (a barge-in or a reply queued
        behind the current one). Such a turn has no end-of-turn metrics, so
        without this it would read as typed."""
        self._gate_replies.append(text)

    def _on_metrics(self, ev) -> None:
        m = ev.metrics
        if isinstance(m, STTMetrics):
            self._turn.stt_audio += m.audio_duration
            took = f", request took {_s(m.duration)}" if not m.streamed else " (streamed realtime)"
            self._event(
                "Speech-to-text", f"{_model(m)} got {m.audio_duration:.1f} s of audio{took}"
            )
        elif isinstance(m, EOUMetrics):
            t = self._turn
            t.eou_delay = m.end_of_utterance_delay
            t.stt_delay = m.transcription_delay
            t.gate_delay = m.on_user_turn_completed_delay
            self._event(
                "Turn end",
                f"caller finished; text ready {_s(m.transcription_delay)} after they stopped, "
                f"turn closed after {_s(m.end_of_utterance_delay)}, "
                f"turn gate took {_s(m.on_user_turn_completed_delay)}",
            )
        elif isinstance(m, LLMMetrics):
            self._turn.llm.append((m.ttft, m.duration))
            state = " (cut off)" if m.cancelled else ""
            self._event(
                "AI model",
                f"{_model(m)}: first words after {_s(m.ttft)}, done in {_s(m.duration)}{state} "
                f"({m.prompt_tokens} tokens in, {m.completion_tokens} out)",
            )
        elif isinstance(m, TTSMetrics):
            self._turn.tts.append((m.ttfb, m.duration, m.audio_duration))
            state = " (cut off)" if m.cancelled else ""
            self._event(
                "Text-to-speech",
                f"{_model(m)}: first audio after {_s(m.ttfb)}, made {m.audio_duration:.1f} s "
                f"of speech in {_s(m.duration)} ({m.characters_count} characters){state}",
            )

    def _on_tool(self, ev) -> None:
        update = ev.update
        if update.type == "tool_call_started":
            call = update.function_call
            self._tool_started[call.call_id] = (call.name, ev.created_at)
            self._event("Tool", f"{call.name} started with {_args(call.arguments)}", ev.created_at)
        elif update.type == "tool_call_ended":
            name, started = self._tool_started.pop(update.call_id, ("?", ev.created_at))
            seconds = ev.created_at - started
            self._turn.tools.append((name, seconds, update.status))
            self._turn.tool_events.append((started, seconds, name, update.status))
            outcome = {"done": "finished", "error": "failed", "cancelled": "was cancelled"}.get(
                update.status, update.status
            )
            self._event("Tool", f"{name} {outcome} after {_s(seconds)}", ev.created_at)

    def _on_item(self, ev) -> None:
        item = ev.item
        if getattr(item, "type", None) != "message":
            return
        if item.role == "user":
            t = self._turn
            t.user_text = item.text_content or ""
            t.gate_reply = t.user_text in self._gate_replies
            if t.gate_reply:
                self._gate_replies.remove(t.user_text)
            t.typed = not t.gate_reply and t.user_stopped_at is None and t.stt_delay is None
            how = "typed" if t.typed else "said"
            note = (
                "spoken while the agent was busy; the turn gate let it through"
                if t.gate_reply
                else "accepted, agent will reply"
            )
            self._event("Caller", f'{how} "{_short(t.user_text)}" ({note})')
        elif item.role == "assistant":
            cut = " (interrupted before finishing)" if item.interrupted else ""
            self._event("Agent", f'said "{_short(item.text_content or "")}"{cut}')
            self._turn.turn_finished_at = self._clock()
            self._summarize(item)
            self._turn_count += 1
            self._turn = _Turn(self._turn_count)

    def _on_close(self, ev) -> None:
        self._write("")
        # participant_disconnected: the browser left (End call button, or end_call).
        reason = getattr(getattr(ev, "reason", None), "value", None)
        self._event("Call", f"ended ({reason})" if reason else "ended", heading=False)
        self._write("")
        self._write("=== Call summary ".ljust(72, "="))
        self._write(_row("Call length", _duration(self._clock() - self._started)))
        self._write(_row("Caller turns answered", str(len(self._responses))))
        if self._responses:
            r = self._responses
            self._write(_row("Average response time", _s(sum(r) / len(r))))
            self._write(_row("Fastest / slowest", f"{_s(min(r))} / {_s(max(r))}"))
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._file.close()

    # ---- turn summary & timeline ----

    def _build_timeline(self, item) -> list[tuple[float, float | None, str, str]]:
        t = self._turn
        events: list[tuple[float, float | None, str, str]] = []

        # 1. Caller spoke & stopped
        if t.user_started_at is not None:
            caller_dur = (t.user_stopped_at - t.user_started_at) if t.user_stopped_at is not None else None
            txt = f'"{_short(t.user_text)}"' if t.user_text else "Voice input"
            events.append((t.user_started_at, caller_dur, "Caller speaking", txt))

        if t.user_stopped_at is not None:
            events.append((t.user_stopped_at, None, "Caller stopped", "Silence detected (turn timing baseline)"))

        # 2. Speech-to-text
        stt_dur = t.stt_delay if t.stt_delay is not None else t.stt_heard_after
        if stt_dur is not None and t.user_stopped_at is not None:
            audio_info = f" ({t.stt_audio:.1f} s audio)" if t.stt_audio else ""
            events.append((t.user_stopped_at, stt_dur, "Speech-to-text", f'heard "{_short(t.user_text or "")}"{audio_info}'))
        elif t.user_stopped_at is not None and t.user_text:
            events.append((t.user_stopped_at, None, "Speech-to-text", f'heard "{_short(t.user_text)}"'))

        # 3. Jev checks
        if t.jev_events:
            for start_at, dur, p in t.jev_events:
                score_str = f"score {p:.2f} out of 1" if p is not None else "no answer"
                events.append((start_at, dur, "Jev check", f"Relevance {score_str}"))
        elif t.jev and t.user_stopped_at is not None:
            total = sum(s for s, _ in t.jev)
            scores = ", ".join("no answer" if p is None else f"{p:.2f}" for _, p in t.jev)
            events.append((t.user_stopped_at + (stt_dur or 0.0), total, "Jev check", f"Relevance score {scores}"))

        # 4. Quick reply filler queued
        if t.filler_event:
            queued_at, f_text, started_after, waited = t.filler_event
            events.append((queued_at, waited, "Quick reply prep", f'Filler queued: "{_short(f_text)}"'))
        elif t.filler and t.user_stopped_at is not None:
            text, after, waited = t.filler
            ref = (t.user_stopped_at + after) if after is not None else t.user_stopped_at
            events.append((ref, waited, "Quick reply prep", f'Filler queued: "{_short(text)}"'))

        # 5. Quick reply speaking
        if t.quick_speaking_at is not None:
            quick_audio = t.tts[0][2] if (t.filler_text and t.tts) else None
            events.append((t.quick_speaking_at, quick_audio, "Quick reply spoke", f'>> FIRST AUDIO: "{_short(t.filler_text or "")}"'))

        # 6. Router / Prefetch
        if t.router_event:
            r_start, r_sec, choice, choice_p, names = t.router_event
            ran = f"ran {', '.join(names)}" if names else "nothing prefetched"
            choice_str = f"{choice} ({choice_p:.2f})" if choice_p is not None else str(choice)
            events.append((r_start, r_sec, "Router / Prefetch", f"Jev chose {choice_str}; {ran}"))
        elif t.router:
            lookup, lookup_p, names, seconds = t.router
            choice = f"{lookup} ({lookup_p:.2f})" if lookup_p is not None else str(lookup)
            ran = f"ran {', '.join(names)}" if names else "nothing prefetched"
            ref = t.thinking_at or t.user_stopped_at or self._started
            events.append((ref, seconds, "Router / Prefetch", f"Jev chose {choice}; {ran}"))

        # 7. Tools
        if t.tool_events:
            for t_start, t_dur, name, status in t.tool_events:
                events.append((t_start, t_dur, f"Tool: {name}", f"status '{status}'"))
        elif t.tools:
            for name, seconds, status in t.tools:
                ref = t.thinking_at or t.user_stopped_at or self._started
                events.append((ref, seconds, f"Tool: {name}", f"status '{status}'"))

        # 8. Main LLM preparation
        if t.thinking_at is not None:
            target_spoke = t.detail_speaking_at or t.speaking_at
            prep_dur = max(0.0, target_spoke - t.thinking_at) if target_spoke else None
            llm_calls_str = f"{len(t.llm)} LLM call(s)" if t.llm else "LLM"
            events.append((t.thinking_at, prep_dur, "Detailed reply prep", f"Main model thinking ({llm_calls_str})"))

        # 9. Detailed reply speaking
        spoke_at = t.detail_speaking_at if t.detail_speaking_at is not None else (t.speaking_at if not t.filler_text else None)
        if spoke_at is not None:
            detailed_audio = sum(a for _, _, a in t.tts[1:]) if (t.filler_text and len(t.tts) > 1) else sum(a for _, _, a in t.tts)
            ans_text = getattr(item, "text_content", None) or ""
            events.append((spoke_at, detailed_audio if detailed_audio > 0 else None, "Detailed reply spoke", f'>> DETAILED ANSWER: "{_short(ans_text)}"'))

        # 10. Turn finished
        if t.turn_finished_at is not None:
            ref = t.user_stopped_at if t.user_stopped_at is not None else (t.user_started_at or self._started)
            total_turn_s = max(0.0, t.turn_finished_at - ref)
            events.append((t.turn_finished_at, None, "Turn finished", f"Agent completed speaking (turn duration: {_s(total_turn_s)})"))

        events.sort(key=lambda x: x[0])
        return events

    def _summarize(self, item) -> None:
        t = self._turn
        if t.turn_finished_at is None:
            t.turn_finished_at = self._clock()

        # Print chronological timeline for voice/interactive turns
        if t.index > 0:
            timeline = self._build_timeline(item)
            if timeline:
                ref_ts = t.user_stopped_at if t.user_stopped_at is not None else (t.user_started_at or self._started)
                ref_str = f"caller stopped: {_wall_time(t.user_stopped_at)}" if t.user_stopped_at else f"baseline: {_wall_time(ref_ts)}"
                self._write("")
                self._write(f"  Turn {t.index} Timeline ({ref_str})")
                self._write("  " + "-" * 88)
                self._write(f"  {'Start Time':<12} {'Offset':<10} {'Duration':<9} {'Step / Phase':<23} Details")
                self._write("  " + "-" * 88)
                for start_t, dur, phase, details in timeline:
                    wall = _wall_time(start_t)
                    off_s = start_t - ref_ts
                    sign = "+" if off_s >= 0 else "-"
                    offset_str = f"[{sign}{abs(off_s):.2f} s]"
                    dur_str = f"{dur:.2f} s" if dur is not None else ""
                    self._write(f"  {wall:<12} {offset_str:<10} {dur_str:<9} {phase:<23} {details}")
                self._write("  " + "-" * 88)

        metrics = item.metrics or {}
        rows: list[tuple[str, str]] = []
        if t.index == 0 and t.user_text is None:
            rows.append(("Caller said", "(nothing, this is the greeting)"))
        else:
            rows.append((f"Caller {'typed' if t.typed else 'said'}", f'"{_short(t.user_text or "")}"'))
        if not t.typed and t.index > 0:
            stt = t.stt_delay if t.stt_delay is not None else t.stt_heard_after
            if stt is not None or not t.gate_reply:
                rows.append(("Speech-to-text", f"{_s(stt)} after the caller stopped"))
            if not t.gate_reply:
                rows.append(("Turn end wait", _s(t.eou_delay)))
        if t.jev:
            total = sum(s for s, _ in t.jev)
            scores = ", ".join("no answer" if p is None else f"{p:.2f}" for _, p in t.jev)
            rows.append(("Jev relevance check", f"{_s(total)} ({_count(len(t.jev), 'check')}, score {scores})"))
        if t.gate_delay:
            rows.append(("Turn gate (incl. Jev)", _s(t.gate_delay)))
        if t.router is not None:
            lookup, lookup_p, names, seconds = t.router
            choice = f"{lookup} ({lookup_p:.2f})" if lookup_p is not None else str(lookup)
            ran = f"ran {', '.join(names)}" if names else "nothing prefetched"
            rows.append(("Router", f"{choice}, {ran}, {_s(seconds)}"))
        if t.filler is not None:
            text, after, waited = t.filler
            when = f", started {_s(after)} after the caller stopped" if after is not None else ""
            rows.append(("Quick reply filler", f'"{_short(text)}"{when}, turn gate waited {_s(waited)}'))
        if t.quick_speaking_at is not None and t.user_stopped_at is not None:
            rows.append(("Quick response started", f"{_s(t.quick_speaking_at - t.user_stopped_at)} after caller stopped"))
        if t.detail_speaking_at is not None and t.user_stopped_at is not None:
            rows.append(("Detailed response started", f"{_s(t.detail_speaking_at - t.user_stopped_at)} after caller stopped"))
        if t.fast is not None:
            rows.append(("Quick reply answer", f"small model {t.fast}"))
        if t.llm:
            total = sum(d for _, d in t.llm)
            calls = ", ".join(_s(d) for _, d in t.llm)
            rows.append(
                ("AI model (LLM)", f"{_s(total)} in {_count(len(t.llm), 'call')} [{calls}], "
                                   f"first words after {_s(t.llm[0][0])}")
            )
        for name, seconds, status in t.tools:
            failed = "" if status == "done" else f" ({status})"
            rows.append((f"Tool: {name}", f"{_s(seconds)}{failed}"))
        if t.tts:
            synth = sum(d for _, d, _ in t.tts)
            audio = sum(a for _, _, a in t.tts)
            rows.append(
                ("Text-to-speech", f"{_s(synth)} for {audio:.1f} s of speech, "
                                   f"first audio after {_s(t.tts[0][0])}")
            )
        target_spoke = t.detail_speaking_at if (t.filler_text and t.detail_speaking_at) else t.speaking_at
        if t.thinking_at is not None and target_spoke is not None:
            prep_s = max(0.0, target_spoke - t.thinking_at)
            note = "(thinking until detailed speech)" if (t.filler_text and t.detail_speaking_at) else "(thinking until speaking)"
            rows.append(("Preparing the reply", f"{_s(prep_s)} {note}"))
        if t.user_stopped_at is not None and t.index > 0:
            first_spoke = t.quick_speaking_at or t.speaking_at
            if first_spoke is not None and first_spoke >= t.user_stopped_at:
                response = first_spoke - t.user_stopped_at
                self._responses.append(response)
                detail_note = ""
                if t.detail_speaking_at and t.detail_speaking_at > first_spoke:
                    detail_note = f" (detailed reply after {_s(t.detail_speaking_at - t.user_stopped_at)})"
                rows.append(("TOTAL RESPONSE TIME", f"{_s(response)} to first speech{detail_note}"))
            elif t.speaking_at is not None and t.thinking_at is not None:
                rows.append(("TOTAL RESPONSE TIME", f"{_s(max(0.0, t.speaking_at - t.thinking_at))} (barge-in or speaking during turn)"))
        elif t.typed and t.thinking_at is not None and t.speaking_at is not None:
            rows.append(("TOTAL RESPONSE TIME", f"{_s(max(0.0, t.speaking_at - t.thinking_at))} (message sent until agent spoke)"))
        elif t.gate_reply and t.thinking_at is not None and t.speaking_at is not None:
            rows.append(("TOTAL RESPONSE TIME", f"{_s(max(0.0, t.speaking_at - t.thinking_at))} (turn gate let it through until agent spoke)"))

        self._write("")
        self._write(f"  Turn {t.index} timing")
        for label, value in rows:
            self._write(_row(label, value))


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _model(m) -> str:
    meta = getattr(m, "metadata", None)
    if meta is not None and (meta.model_provider or meta.model_name):
        return f"{meta.model_provider or '?'}/{meta.model_name or '?'}"
    return m.label


def _args(arguments: str | None) -> str:
    try:
        args = json.loads(arguments or "{}")
    except (TypeError, ValueError):
        return _short(arguments or "")
    if isinstance(args, dict):
        return _short(", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items()) or "no arguments")
    return _short(json.dumps(args, ensure_ascii=False))
