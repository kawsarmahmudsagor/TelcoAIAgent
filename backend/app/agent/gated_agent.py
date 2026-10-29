"""Voice turn gate: the agent ignores speech that isn't the customer talking to it.

Self-hosted LiveKit has no Cloud noise cancellation, and nothing in the browser
removes *other people talking*. So every voice turn is checked before the agent
answers it: cheap pre-checks (app.agent.turn_gate) and, where those don't settle
it, the Jev relevance judge (app.agent.turn_judge).

- Bot listening: a finished turn is accepted or dropped silently (decide());
  speech in another language may get one fixed "could you repeat that?" line.
  Gated sessions have preemptive generation off, so the LLM only ever sees
  accepted turns.
- Bot busy (thinking/speaking): the session runs with library interruption off,
  so nothing cuts the bot off on its own. The gate interrupts it only for a stop
  phrase or speech the judge rates as addressed. Overlapping speech it doesn't
  act on is dropped by the library (a turn ending during uninterruptible speech
  is skipped).
- Accepted voice turns are sent to the browser on USER_TURN_TOPIC; the frontend
  shows only those, not the raw transcription of everything the mic heard.
  Ungated browser sessions (TurnPublishingAgent) publish every voice turn the
  agent answers the same way, so the transcript works alike in both modes.

Typed chat never reaches on_user_turn_completed. In gated sessions it is judged
for topic only (it's always meant for the agent): an off-topic request isn't
answered, doesn't interrupt the agent, and is taken off the browser's transcript
(IGNORED_TEXT_TOPIC).

Until the greeting has played out (userdata.greeting_done) the gate ignores
transcripts entirely: no barge-in, no queued answer, no turn accepted.
"""

import asyncio
import json
import logging
import re
import time
from collections import deque
from collections.abc import AsyncIterable, Callable, Coroutine
from dataclasses import dataclass, field, replace
from typing import Any

import httpx
import numpy as np
from livekit import rtc
from livekit.agents import Agent, AgentSession, StopResponse, llm
from livekit.agents.types import FlushSentinel
from livekit.agents import room_io
from livekit.agents.voice.events import UserInputTranscribedEvent

from app.agent import (
    cards,
    closing_offer,
    quick_reply,
    reply_punctuation,
    turn_gate,
    turn_judge,
    voice_level,
)
from app.agent.prefetch import Prefetcher
from app.agent.quick_reply import QuickReplyRuntime
from app.agent.turn_gate import GateState, Thresholds, Verdict
from app.agent.turn_judge import BotState, Exchange, Judgement
from app.config import Settings
from app.services.phone_numbers import spoken_digits_in_text

logger = logging.getLogger("agent.turn_gate")

USER_TURN_TOPIC = "user-turn"
# Set to "1" on every browser session, gated or not: the agent publishes the
# voice turns it takes on USER_TURN_TOPIC, and the frontend shows only those.
# (The name predates ungated sessions publishing them too.)
GATE_ATTRIBUTE = "turn_gate"
# A typed message the agent ignored (off-topic): {"id": <its text stream id>}, so
# the browser can drop it from the transcript.
IGNORED_TEXT_TOPIC = "ignored-text"

OTHER_LANGUAGE_LINE = "I could not understand that. Could you kindly repeat that?"
# Said when a turn the gate dropped still reads like a question to the agent.
UNCLEAR_TURN_LINE = "সরি, ঠিক বুঝতে পারিনি। আরেকবার বলবেন?"
# Said when the turn's processing or the main model's reply fails.
STREAM_FAILED_LINE = "সরি, একটু সমস্যা হচ্ছে। আরেকবার বলবেন, প্লিজ?"

# A dropped turn that still reads like a question to the agent gets "please say
# that again" instead of silence. Bengali vowel signs aren't word characters, so
# the Bangla words have no \b around them.
_QUESTION_OR_ADDRESS_RE = re.compile(
    r"\?|？|কি|কী|কেমন|কত|কোথায়|কোন|কখন|কবে|কেন|আছে|বলবেন|শুনতে|ভাই|আপু|ম্যাডাম|স্যার|"
    r"ব্যালেন্স|প্যাক|ডাটা|মিনিট|রিচার্জ|নেটওয়ার্ক|অফার|টাকা|"
    r"\b(?:balance|pack|data|minutes?|recharge|network|offer|price)\b",
    re.I,
)


def _has_question_or_address(text: str) -> bool:
    return bool(_QUESTION_OR_ADDRESS_RE.search(text))

# STT language codes (ISO 639-1 and -3, region dropped) a customer's turn may carry.
_CUSTOMER_LANGUAGES = frozenset({"bn", "ben", "en", "eng"})

# How long frames under the voice isolation bar still pass after a louder one:
# protects soft word endings and the gaps between words.
_ISOLATION_HANGOVER_S = 0.35

# Assent words ("হ্যাঁ", "জি") are said softer still: this much more margin.
_ASSENT_EXTRA_MARGIN_DB = 8.0

_BUSY_STATES = {"initializing", "thinking", "speaking"}
_HISTORY_MESSAGES = 4
# Voice providers whose STT writes Bangla in Bengali script. Deepgram (also the
# fallback inside the ElevenLabs chain) renders it in Latin or Devanagari.
_BENGALI_STT_PROVIDERS = {"elevenlabs", "openrouter"}

# judge(text, bot_state, route=False): route asks the lookup question too
# (finished listening turns only, when the router is on).
JudgeFn = Callable[..., Coroutine[Any, Any, Judgement]]


@dataclass(frozen=True)
class PauseConfig:
    """When speech over the agent pauses it (see TurnGateController.on_audio_level)."""

    min_speech_s: float
    margin_db: float
    fallback_dbfs: float
    resume_after_s: float
    max_pause_s: float
    # The judge's bar for speech that paused the agent, instead of interrupt_p.
    interrupt_p: float = 0.4


@dataclass(frozen=True)
class GateConfig:
    thresholds: Thresholds
    interrupt_p: float
    interrupt_min_words: int
    stt_writes_bengali: bool
    # None: speech over the agent never pauses it, only the judge stops it.
    pause: PauseConfig | None = None
    # Voice isolation (settings.turn_voice_isolation_enabled and its bars).
    voice_isolation_enabled: bool = False
    speech_margin_db: float = 10.0
    speech_floor_dbfs: float = -42.0


def pause_config(settings: Settings) -> PauseConfig | None:
    if not settings.turn_pause_enabled:
        return None
    return PauseConfig(
        min_speech_s=settings.turn_pause_min_speech_s,
        margin_db=settings.turn_pause_margin_db,
        fallback_dbfs=settings.turn_pause_fallback_dbfs,
        resume_after_s=settings.turn_pause_resume_after_s,
        max_pause_s=settings.turn_pause_max_s,
        interrupt_p=settings.turn_pause_interrupt_p,
    )


def gate_config(settings: Settings, stt_tts_provider: str) -> GateConfig:
    return GateConfig(
        thresholds=Thresholds(
            drop_p=settings.turn_drop_p,
            min_confidence=settings.turn_min_confidence,
            other_language_cooldown_s=settings.turn_other_language_cooldown_s,
        ),
        interrupt_p=settings.turn_interrupt_p,
        interrupt_min_words=settings.turn_interrupt_min_words,
        stt_writes_bengali=stt_tts_provider in _BENGALI_STT_PROVIDERS,
        pause=pause_config(settings),
        voice_isolation_enabled=settings.turn_voice_isolation_enabled,
        speech_margin_db=settings.turn_speech_margin_db,
        speech_floor_dbfs=settings.turn_speech_floor_dbfs,
    )


def jev_judge(
    session: AgentSession,
    settings: Settings,
    api_key: str,
    client: httpx.AsyncClient,
    on_judged: Callable[[str, BotState, float, float | None], None] | None = None,
    *,
    router: bool = False,
    knowledge_base: bool = False,
) -> JudgeFn:
    """A JudgeFn that asks Jev, with the last few exchanges as context.
    on_judged gets (text, bot_state, seconds, p) after every call. With router
    on, a routed call also asks which lookup the reply needs (knowledge_base:
    whether the knowledge base is one of the options)."""
    url = turn_judge.decisions_url(settings.openrouter_base_url)
    timeout_s = settings.turn_judge_timeout_ms / 1000

    async def _judge(
        text: str, bot_state: BotState, route: bool = False, speaking: str = ""
    ) -> Judgement:
        lookup = router and route
        history = _recent_exchanges(session)
        # What the agent is saying right now joins the history only once it
        # stops: without it "দুইটা দেখান" over a list of packages reads as
        # garble (run_27: 0.12).
        if speaking.strip() and not (history and history[-1].text == speaking):
            history.append(Exchange("assistant", f"{speaking.strip()} …"))
        payload = turn_judge.build_request(
            settings.turn_judge_model,
            history,
            text,
            bot_state,
            turn_gate.address_form(text),
            lookup=lookup,
            knowledge_base=knowledge_base,
        )
        started = time.perf_counter()
        judgement = await turn_judge.judge(client, url, api_key, payload, timeout_s, utterance=text)
        if on_judged is not None:
            on_judged(text, bot_state, time.perf_counter() - started, judgement.p)
        return judgement

    return _judge


# Nobody waits on the warm-up, so it may take as long as a cold start needs.
_JUDGE_WARM_TIMEOUT_S = 10.0


def jev_warm_up(
    settings: Settings,
    api_key: str,
    client: httpx.AsyncClient,
    *,
    router: bool = False,
    knowledge_base: bool = False,
) -> Callable[[], Coroutine[Any, Any, None]]:
    """One throwaway Jev request, shaped like a real first turn's, to send
    while the greeting plays. Otherwise the first real one pays for Jev's cold
    start and can hit the judge timeout, and the customer's first turn goes
    through unjudged, someone nearby included."""
    url = turn_judge.decisions_url(settings.openrouter_base_url)

    async def _warm() -> None:
        payload = turn_judge.build_request(
            settings.turn_judge_model,
            [],
            "hello",
            "listening",
            turn_gate.address_form("hello"),
            lookup=router,
            knowledge_base=knowledge_base,
        )
        await turn_judge.judge(client, url, api_key, payload, _JUDGE_WARM_TIMEOUT_S)

    return _warm


def _recent_exchanges(session: AgentSession) -> list[Exchange]:
    out: list[Exchange] = []
    for item in session.history.items:
        if getattr(item, "type", None) != "message" or item.role not in ("user", "assistant"):
            continue
        if text := item.text_content:
            out.append(Exchange(item.role, text))
    return out[-_HISTORY_MESSAGES:]


_PROMPT_ENDINGS_BN = (
    "বলবেন", "জানাবেন", "করবেন", "করব", "করবো", "চান", "লাগবে", "হবে", "কি", "কী",
)

_CONFIRM_OR_ASSENT_WORDS = {
    "জি", "হ্যাঁ", "হুম", "হ্যা", "হাঁ", "জিহ", "yes", "yeah", "yep", "sure", "ok", "okay",
    "করেন", "করুন", "নিশ্চিত", "কনফার্ম", "confirm", "হবে", "চাই", "রাখুন", "রাখেন",
    "না", "no", "nope", "not", "লাগবে না", "দরকার নেই", "না না", "নেই", "না ভাই", "না আপু",
}


# A yes to a waiting action (recharge, purchase, redeem) or a cancel: often said
# softly, after the agent read numbers back.
_CONFIRM_RE = re.compile(
    r"confirm|কনফার্ম|নিশ্চিত|বাতিল|cancel|"
    r"(?:জি|হ্যাঁ|হুম)\s*(?:করুন|করেন|করে\s*(?:দিন|দেন)|দিন|দেন|ঠিক\s*আছে|কিনুন|নিন)|"
    r"(?:কিনে|রিচার্জ\s*করে|চালু\s*করে)\s*(?:দিন|দেন)|"
    r"\b(?:go\s+ahead|do\s+it|buy\s+it)\b",
    re.I,
)


def _is_confirmation_or_assent(text: str) -> bool:
    if _CONFIRM_RE.search(text):
        return True
    ws = turn_gate.words(text)
    if not ws:
        return False
    return len(ws) <= 4 and any(w in _CONFIRM_OR_ASSENT_WORDS for w in ws)


def _bot_just_asked(session: AgentSession) -> bool:
    """Whether the latest message of the conversation is the agent's, ending
    in a question or polite prompt. Tool calls and config updates in between don't count."""
    for item in reversed(session.history.items):
        if getattr(item, "type", None) != "message" or item.role not in ("user", "assistant"):
            continue
        if item.role != "assistant":
            return False
        text = (item.text_content or "").rstrip()
        if text.endswith(("?", "？")):
            return True
        tail = text[-35:] if len(text) > 35 else text
        if any(w in tail for w in _PROMPT_ENDINGS_BN):
            return True
        return False
    return False


@dataclass
class _Handled:
    text: str | None = None
    at: float = 0.0
    # Jev's answers for an approved barge-in, so its turn is routed without a second call.
    judgement: Judgement | None = None


@dataclass
class _PendingFiller:
    """A filler line still being written when its turn's lookup finished: the
    reply goes ahead and with_filler speaks the line if it is ready first."""

    message_id: str
    text: str
    task: asyncio.Task[str | None]
    started: float


@dataclass
class _Hook:
    """An accepted turn still in on_user_turn_completed: a reply the gate makes
    meanwhile (barge-in, queued answer) waits for it, so the turn's own reply
    and question are settled first."""

    message: llm.ChatMessage
    done: asyncio.Event = field(default_factory=asyncio.Event)
    prefetch: asyncio.Task | None = None


@dataclass
class TurnGateController:
    """Per-session gate state plus the session event handlers. Event handlers
    are sync (session.on rejects coroutines) and spawn tasks."""

    session: AgentSession
    room: rtc.Room | None
    config: GateConfig
    judge: JudgeFn
    clock: Callable[[], float] = time.monotonic
    # Told the text of each turn the gate answers itself (barge-in, queued), which
    # never goes through the library's end-of-turn path.
    on_gate_reply: Callable[[str], None] | None = None
    # The turn router (app.agent.prefetch), when on: runs an accepted turn's
    # lookup before the LLM.
    prefetcher: Prefetcher | None = None
    # Quick replies (app.agent.quick_reply), when on: a filler line while a
    # lookup runs, and the small model answering turns that need none.
    quick: QuickReplyRuntime | None = None
    # (line, seconds after the caller's last words, seconds waited) per filler (run_log).
    on_filler: Callable[[str, float | None, float], None] | None = None
    # (user message id, line): stores the filler after its turn (transcript).
    on_filler_store: Callable[[str, str], None] | None = None
    # (line) for a filler said in front of the reply (with_filler): its
    # transcription is held back from the reply's, so the browser is sent it
    # this way, as session.say's fillers reach it on their own.
    on_filler_shown: Callable[[str], None] | None = None
    # (handed_off) for each turn the small model takes (run_log).
    on_fast: Callable[[bool], None] | None = None
    # What became of speech over the agent: paused, resumed, interrupted,
    # queued (run_log).
    on_barge_in: Callable[[str], None] | None = None
    # A throwaway judge call for warm() (see jev_warm_up).
    warm_judge: Callable[[], Coroutine[Any, Any, None]] | None = None

    state: GateState = field(default_factory=GateState)
    _buffer: list[str] = field(default_factory=list)
    _bot_texts: deque[str] = field(default_factory=lambda: deque(["", ""], maxlen=2))
    _judged: dict[str, asyncio.Task[Judgement]] = field(default_factory=dict)
    # A barge-in the gate answered itself: the library's own turn for it is dropped.
    _answered: _Handled = field(default_factory=_Handled)
    # A barge-in let through while the user was still talking: the library delivers
    # the full turn, which is then accepted without asking the judge again.
    _approved: _Handled = field(default_factory=_Handled)
    _barge_in_running: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _tasks: set[asyncio.Task] = field(default_factory=set)
    # Pausing the agent on loud speech over it (see on_audio_level).
    _level: voice_level.CallerLevel = field(default_factory=voice_level.CallerLevel)
    _loud: voice_level.LoudSpeech | None = None
    _paused_at: float | None = None
    _last_voice_at: float = 0.0
    # The speech just rejected must not pause the agent again until it stops.
    _pause_vetoed: bool = False
    # Speech at the customer's own level paused the agent and no barge-in
    # decision has used that yet. Kept past a quiet resume: the transcript and
    # the judge can land after the pause has already let go (run_47: 3.05 s).
    _loud_heard: bool = False
    # Quick replies: filler lines being written, keyed by normalized text; when
    # the latest STT final arrived; counters a waiting turn compares against.
    _fillers: dict[str, asyncio.Task[str | None]] = field(default_factory=dict)
    _final_at: float | None = None
    _barge_ins: int = 0
    _hook: _Hook | None = None
    _filler_handle: Any = None
    # The turn's filler, handed to llm_node (with_filler); the next segment the
    # transcription node sees is that line, which stays out of the chat context.
    pending_filler: _PendingFiller | None = None
    _filler_segment: bool = False
    # The user message whose reply the small model writes (GatedAgent.llm_node).
    fast_for: str | None = None
    _judge_warmed: bool = False

    def __post_init__(self) -> None:
        if self.config.pause is not None:
            self._loud = voice_level.LoudSpeech(self.config.pause.min_speech_s)

    def attach(self) -> None:
        self.session.on("user_input_transcribed", self.on_user_input_transcribed)
        self.session.on("agent_state_changed", self._on_agent_state_changed)

    @property
    def caller_reference(self) -> float | None:
        """The customer's learned speaking level (dBFS), or None before their
        first accepted turn."""
        return self._level.reference

    def warm(self) -> None:
        """Starts the judge's warm-up, once; nothing waits for it."""
        if self.warm_judge is not None and not self._judge_warmed:
            self._judge_warmed = True
            self._spawn(self.warm_judge())

    # ---- agent speech, for the echo check ----

    def bot_reply_started(self) -> None:
        self._bot_texts.append("")

    def bot_said(self, delta: str) -> None:
        self._bot_texts[-1] += delta

    # ---- events ----

    def _on_agent_state_changed(self, ev) -> None:
        # A new agent turn starts a new user turn; a turn the library dropped
        # (spoken over uninterruptible speech) leaves no other trace.
        if ev.new_state in ("thinking", "speaking"):
            self._buffer.clear()
        if self._filler_playing():
            # The reply going to "thinking" mid-filler must not let a paused
            # filler play on, nor drop the caller's level.
            return
        if ev.new_state != "speaking":
            self.release_pause()
            self._loud_heard = False
        if ev.new_state == "listening":
            self._level.clear()

    # ---- pause on loud speech (bot speaking) ----

    def on_audio_level(self, db: float, duration_s: float) -> None:
        """One mic frame's level. While the agent speaks, speech within margin_db
        of the customer's own level for min_speech_s pauses it at once; the
        judge then interrupts it (barge-in) or it resumes. Frames heard while it
        listens calibrate that level once the gate accepts the turn (the pause and
        voice isolation both use it, so it is learned when either is on)."""
        pause = self.config.pause
        if pause is None and not self.config.voice_isolation_enabled:
            return
        user_speaking = self.session.user_state == "speaking"
        agent_state = self.session.agent_state
        if self._filler_playing():
            agent_state = "speaking"
        if agent_state == "listening" and user_speaking:
            self._level.heard(db)
        if pause is None or self._loud is None:
            return

        now = self.clock()
        if user_speaking:
            self._last_voice_at = now
        else:
            self._pause_vetoed = False
            self._loud.reset()
        if self._paused_at is not None:
            if now - self._last_voice_at >= pause.resume_after_s:
                self._resume("quiet")
            elif now - self._paused_at >= pause.max_pause_s:
                self._resume("too_long")
            return
        if not (
            user_speaking
            and agent_state == "speaking"
            and not self._pause_vetoed
            and self._greeting_done()
        ):
            return
        bar = self._level.threshold(margin_db=pause.margin_db, fallback_dbfs=pause.fallback_dbfs)
        if self._loud.update(db, duration_s, bar):
            self._pause(db, bar)

    def release_pause(self) -> None:
        """Lets the audio output play again after the agent was interrupted or
        stopped speaking; a no-op when it isn't paused."""
        if self._paused_at is None:
            return
        self._paused_at = None
        if self._loud is not None:
            self._loud.reset()
        if (audio := self.session.output.audio) is not None:
            audio.resume()

    def _pause(self, db: float, bar: float) -> None:
        audio = self.session.output.audio
        if audio is None or not audio.can_pause:
            return
        audio.pause()
        self._paused_at = self.clock()
        self._loud_heard = True
        logger.info("turn gate pause: %.1f dBFS over a bar of %.1f", db, bar)
        self._note(f"paused the agent: voice at the caller's level ({db:.0f} dBFS)")

    def _resume(self, reason: str) -> None:
        """A pause that ends without a barge-in: the agent carries on, and the
        same speech doesn't pause it again."""
        if self._paused_at is None:
            return
        self.release_pause()
        self._pause_vetoed = True
        logger.info("turn gate resume: %s", reason)
        self._note(f"agent resumed ({reason})")

    def _note(self, what: str) -> None:
        if self.on_barge_in is not None:
            self.on_barge_in(what)

    def reset(self) -> None:
        """Forgets per-turn state: speech heard during the greeting must not
        join the customer's first real turn."""
        self._buffer.clear()
        self._judged.clear()
        self._answered = _Handled()
        self._approved = _Handled()
        self._cancel_fillers()
        self.fast_for = None
        if self.prefetcher is not None:
            self.prefetcher.cancel()

    def _greeting_done(self) -> bool:
        return self.session.userdata.greeting_done

    def on_user_input_transcribed(self, ev: UserInputTranscribedEvent) -> None:
        if not self._greeting_done():
            # The greeting can't be interrupted, so nothing heard during it may
            # barge in (interrupt(force=True) ignores allow_interruptions) or be
            # queued as an answer.
            return

        raw = (ev.transcript or "").strip()
        # Drop non-speech sound tags: [background noise], [crosstalk], [笑], (laughter), etc.
        if not raw or turn_gate.is_sound_only(raw):
            return

        # Quiet noise comes back as text in some other language (Polish, Turkish,
        # Malayalam); customers speak only Bangla or English.
        lang = (getattr(ev, "language", "") or "").lower().split("-")[0]
        if lang and lang not in _CUSTOMER_LANGUAGES:
            logger.info("ignoring transcript in language %r: %r", lang, raw)
            return

        if ev.is_final:
            self._buffer.append(ev.transcript)
            text = " ".join(self._buffer)
        else:
            text = " ".join([*self._buffer, ev.transcript])

        bot_state = self.session.agent_state
        if self._filler_playing():
            # A filler is the agent speaking, even in the gap before the reply's
            # audio when the library already says "listening" or "thinking".
            bot_state = "speaking"
        if bot_state not in _BUSY_STATES:
            if ev.is_final:
                self._final_at = self.clock()
                # Starts now, overlapping endpointing; on_user_turn_completed awaits it.
                judged = self._judge_cached(text, "listening")
                if self.quick is not None and self.quick.filler:
                    self._cancel_fillers()
                    judged.add_done_callback(lambda task, text=text: self._on_judged(text, task))
                if self.prefetcher is not None:
                    self.prefetcher.start(text, _recent_exchanges(self.session))
            return
        self._spawn(self._consider_barge_in(text, ev.is_final, _bot_state(bot_state)))

    # ---- barge-in (bot busy) ----

    def _forget_judged(self, judged: int) -> None:
        """Drops the finals a barge-in decision covered, so a rejected line never
        joins later speech and gets judged again with it (run_52: a bystander's
        0.10 plus two noise finals came to 0.27). Finals that arrived while the
        judge ran are judged next."""
        del self._buffer[:judged]

    async def _consider_barge_in(self, text: str, is_final: bool, bot_state: BotState) -> None:
        text = turn_gate.clean_transcript(text)
        if not text or turn_gate.is_sound_only(text):
            return
        now = self.clock()
        judged = len(self._buffer)
        if turn_gate.matches_handled(text, self._answered.text, now - self._answered.at):
            return
        if turn_gate.matches_handled(text, self._approved.text, now - self._approved.at):
            return
        if turn_gate.is_echo(text, list(self._bot_texts)):
            if is_final:
                self._resume("echo")
                self._forget_judged(judged)
            return
        pre = turn_gate.precheck(text, None)
        if not turn_gate.needs_judge(pre, stt_writes_bengali=self.config.stt_writes_bengali):
            if is_final:
                self._resume("not_speech" if pre.script != "other" else "other_language")
                self._forget_judged(judged)
            return

        # A stop phrase interrupts without the judge while the caller is still
        # saying it, and the whole sentence is judged once it arrives. A whole
        # sentence that only opens with one is judged like any other: a bystander's
        # "না, না, আর উপর থেকে নিচে নামার জন্য কী করতে হবে" was answered in place of
        # the customer's question.
        stop = turn_gate.is_stop_phrase(text) and (
            not is_final or turn_gate.is_bare_stop_phrase(text)
        )
        p: float | None = None
        judgement: Judgement | None = None
        if not stop:
            if not is_final or self._barge_in_running:
                return
            self._barge_in_running = True
            try:
                judgement = await self._judge_cached(text, bot_state)
                p = judgement.p
            finally:
                self._barge_in_running = False
            if p is None:
                self._resume("judge_failed")
                self._forget_judged(judged)
                return
            # Speech that paused the agent sounds like the customer (their own
            # level, not the speakers), so it needs a lower score to interrupt.
            # Not as low as drop_p: people nearby can be as loud (run_53, 0.25-0.30)
            # while real questions over the agent scored 0.43-0.50 (run_47).
            loud = self._loud_heard
            self._loud_heard = False
            pause = self.config.pause
            bar = pause.interrupt_p if loud and pause is not None else self.config.interrupt_p
            long_enough = pre.word_count >= self.config.interrupt_min_words
            if not (long_enough and p >= bar):
                self._resume(f"rejected, score {p:.2f}")
                self._forget_judged(judged)
                # Speech over the agent that didn't interrupt it is dropped, never
                # answered later: quieter than the customer and below the bar, it
                # was someone nearby (run_54: 0.45, no pause, then answered). A
                # short answer while the agent looks something up is queued
                # behind the current reply rather than lost.
                if bot_state == "thinking" and p >= self.config.thresholds.drop_p:
                    await self._answer_after_current(text, p)
                return

        async with self._lock:
            await self._barge_in(text, stop=stop, p=p, judgement=judgement)

    async def _barge_in(
        self, text: str, *, stop: bool, p: float | None, judgement: Judgement | None = None
    ) -> None:
        text = turn_gate.clean_transcript(text)
        # A turn still waiting in on_user_turn_completed (on its filler or
        # lookup) is now stale: it keeps its question but drops its reply.
        self._barge_ins += 1
        self._cancel_fillers()
        self.fast_for = None
        hook = self._hook
        if hook is not None and hook.prefetch is not None:
            hook.prefetch.cancel()
        now = self.clock()
        if self.session.user_state == "speaking":
            # Still talking: stop the agent and let the library deliver the whole
            # sentence as a normal turn ("না না, ... বনানী"), accepted on arrival.
            self._approved = _Handled(text, now, judgement)
            await self.session.interrupt(force=True)
            self.release_pause()
            self._note("interrupted the agent; the caller is still talking")
            _log("barge_in_interrupt", text, p=p, stop=stop)
            return
        await self.session.interrupt(force=True)
        self.release_pause()
        self._note("interrupted the agent to answer the caller")
        self.session.clear_user_turn()
        self._answered = _Handled(text, now)
        self._buffer.clear()
        self.state.record(Verdict.ACCEPT, now)
        await self._publish_user_turn(text)
        self._gate_reply(text)
        await self._after_hook()
        self._route_barge_in(text, judgement)
        self.session.generate_reply(user_input=text, input_modality="audio")
        _log("barge_in_reply", text, p=p, stop=stop)

    def _route_barge_in(self, text: str, judgement: Judgement | None) -> None:
        """A barge-in the gate answers itself (generate_reply, so no
        on_user_turn_completed) takes the same quick path as a finished turn
        (_run_accepted): the filler line is handed to the reply, or the small
        model answers. The reply's user message doesn't exist yet, so the route
        is keyed on its text (_is_reply_to)."""
        self.pending_filler = None
        self.fast_for = None
        if self.quick is None or judgement is None:
            return
        path = quick_reply.route(
            judgement, self.session.userdata, self.quick.config, self.quick.settings, text=text
        )
        key = _text_key(text)
        if path == "fast":
            self.fast_for = key
        elif path == "filler":
            task = self._filler_task(text, judgement)
            self.pending_filler = _PendingFiller(key, text, task, self.clock())

    async def _answer_after_current(self, text: str, p: float) -> None:
        text = turn_gate.clean_transcript(text)
        async with self._lock:
            now = self.clock()
            self._answered = _Handled(text, now)
            self._buffer.clear()
            self.state.record(Verdict.ACCEPT, now)
            await self._publish_user_turn(text)
            self._gate_reply(text)
            # The turn being answered goes first: its reply is scheduled when its
            # hook returns.
            await self._after_hook()
            self.session.generate_reply(user_input=text, input_modality="audio")
            self._note("answer queued after the current reply")
            _log("queued_reply", text, p=p)

    # ---- finished turn (bot was listening) ----

    async def on_user_turn_completed(
        self, new_message: llm.ChatMessage, turn_ctx: llm.ChatContext | None = None
    ) -> None:
        """Returns to let the turn through; raises StopResponse to drop it. An
        accepted turn's lookup is prefetched into turn_ctx (see app.agent.prefetch)."""
        self._buffer.clear()
        now = self.clock()
        raw_text = new_message.text_content or ""
        if not self._greeting_done() or (
            not turn_gate.normalize(raw_text) and not turn_gate.has_contact(raw_text)
        ):
            raise StopResponse()
        # Sound tags ("[clears throat]") stay out of the conversation the agent
        # and the transcript see; a turn that is only tags was dropped above. A
        # phone number said as words reaches the agent as digits.
        text = spoken_digits_in_text(turn_gate.clean_transcript(new_message.text_content or ""))
        if text != new_message.text_content:
            new_message.content = [text]
        if (userdata := _userdata(self)) is not None:
            # The package cards show only what this turn asks about.
            userdata.turn_text = text
        if turn_gate.matches_handled(text, self._answered.text, now - self._answered.at):
            _log("deduped", text)
            raise StopResponse()
        if turn_gate.matches_handled(text, self._approved.text, now - self._approved.at):
            approved, judgement = self._approved.text or "", self._approved.judgement
            self._approved = _Handled()
            # The barge-in was judged on what had been heard so far. A fragment can
            # look addressed on its own ("সম্পর্কে বলুন" 0.71) while the whole turn is
            # off-topic ("বাংলাদেশের ক্রিকেট টিম সম্পর্কে বলুন" 0.05), so a longer turn
            # is judged again.
            if turn_gate.normalize(text) != turn_gate.normalize(approved):
                judgement = await self._judge_cached(text, "listening")
                p = judgement.p
                if p is not None and p < self.config.thresholds.drop_p:
                    self.state.record(Verdict.DROP, now)
                    _log("drop_barge_in", text, p=p, approved=approved)
                    raise StopResponse()
            self.state.record(Verdict.ACCEPT, now)
            await self._publish_user_turn(text)
            _log("accept_barge_in", text)
            # The same quick path as any accepted turn, on the judgement that
            # approved the barge-in (no second Jev call for the same words).
            await self._run_accepted(text, judgement, turn_ctx, new_message)
            return

        if self.config.voice_isolation_enabled:
            await self._drop_quiet_voice(text, new_message.transcript_confidence, now)

        started = time.perf_counter()
        pre = turn_gate.precheck(text, new_message.transcript_confidence)
        is_confirm = _is_confirmation_or_assent(text)
        judgement: Judgement | None = None
        if turn_gate.needs_judge(pre, stt_writes_bengali=self.config.stt_writes_bengali):
            judgement = await self._judge_cached(text, "listening")
        p = judgement.p if judgement is not None else None
        verdict = turn_gate.decide(
            pre,
            p,
            stt_writes_bengali=self.config.stt_writes_bengali,
            state=self.state,
            now=now,
            th=self.config.thresholds,
            bot_asked=(pre.assent or is_confirm) and _bot_just_asked(self.session),
        )
        self.state.record(verdict, now)
        _log(verdict.value, text, p=p, pre=pre, ms=(time.perf_counter() - started) * 1000)
        # Only the customer's own words set their level: not a dropped turn
        # (someone else), not a soft "hmm".
        if verdict is Verdict.ACCEPT and not pre.filler:
            self._level.accept()
        else:
            self._level.clear()

        if verdict is Verdict.ACCEPT:
            await self._publish_user_turn(text)
            try:
                await self._run_accepted(text, judgement, turn_ctx, new_message, closing=pre.closing)
            except StopResponse:
                raise
            except Exception as exc:
                logger.exception("Error during accepted turn processing; proceeding to LLM: %s", exc)
                self._cancel_fillers()
                if self.prefetcher is not None:
                    self.prefetcher.cancel()
            return
        self._cancel_fillers()
        if self.prefetcher is not None:
            self.prefetcher.cancel()
        if verdict is Verdict.OTHER_LANGUAGE:
            self.session.say(OTHER_LANGUAGE_LINE, add_to_chat_ctx=False)
            raise StopResponse()
        if verdict is Verdict.DROP:
            # If the user spoke substantive words (not pure filler, silence or sound tags)
            # but it was dropped (e.g. low Jev score or unclear speech):
            # Clarify so the agent never stays stuck or silent.
            if (
                self.session.current_speech is None
                and (p is None or p >= 0.20)
                and turn_gate.address_form(text) != "informal"
                and pre.word_count >= 2
                and not pre.filler
                and not turn_gate.is_sound_only(text)
            ):
                if _has_question_or_address(text):
                    logger.info("Turn was dropped by gate but contains question/address; asking clarification: %s", text)
                    try:
                        self.session.say(UNCLEAR_TURN_LINE, add_to_chat_ctx=True)
                    except Exception:
                        pass
        raise StopResponse()

    async def _drop_quiet_voice(self, text: str, confidence: float | None, now: float) -> None:
        """Voice isolation: raises StopResponse for a turn too quiet to be the
        customer (they sit nearest the mic). Below the floor it is someone across
        the room; more than the margin below the caller's learned level, someone
        nearby. Soft answers to the agent's question ("জি করেন", a code read back)
        often come 15-20 dB under the caller's peak, so an answer or a
        confirmation skips the margin and survives the floor when Jev rates it
        addressed; any other quiet turn survives only that way too."""
        turn_db = self._level.current_turn_level()
        if turn_db is None:
            return
        answer = _bot_just_asked(self.session) or _is_confirmation_or_assent(text)
        floor = self.config.speech_floor_dbfs
        if turn_db < floor:
            if answer and await self._judged_addressed(text):
                logger.info("quiet answer kept: %.1f dBFS under floor %.1f: %s", turn_db, floor, text)
                return
            self._drop_isolated("drop_distant_voice", text, now, db=round(turn_db, 1), floor=floor)
        ref = self._level.reference
        if ref is None or answer:
            return
        margin = self.config.speech_margin_db
        if turn_gate.precheck(text, confidence).assent:
            margin += _ASSENT_EXTRA_MARGIN_DB
        if turn_db >= ref - margin:
            return
        if await self._judged_addressed(text):
            logger.info(
                "quiet turn kept: %.1f dBFS, %.1f dB under the caller, Jev rates it addressed: %s",
                turn_db, ref - turn_db, text,
            )
            return
        self._drop_isolated("drop_surrounding_voice", text, now, db=round(turn_db, 1), ref=round(ref, 1))

    async def _judged_addressed(self, text: str) -> bool:
        judgement = await self._judge_cached(text, "listening")
        return judgement.p is not None and judgement.p >= self.config.thresholds.drop_p

    def _drop_isolated(self, event: str, text: str, now: float, **fields) -> None:
        self._level.clear()
        self.state.record(Verdict.DROP, now)
        _log(event, text, **fields)
        raise StopResponse()

    async def _run_accepted(
        self,
        text: str,
        judgement: Judgement | None,
        turn_ctx: llm.ChatContext | None,
        new_message: llm.ChatMessage,
        *,
        closing: bool = False,
    ) -> None:
        """An accepted turn's work before its reply: the prefetched lookup, and
        with quick replies the route and the filler line. A barge-in meanwhile
        keeps the turn's question in the conversation but drops its reply."""
        hook = _Hook(new_message)
        self._hook = hook
        seen_barge_ins = self._barge_ins
        self.pending_filler = None
        if (userdata := getattr(self.session, "userdata", None)) is not None:
            userdata.wrap_up = closing_offer.wraps_up(
                judgement.wrap_up_p if judgement is not None else None, text
            )
        try:
            path = None
            if self.quick is not None:
                path = quick_reply.route(
                    judgement,
                    self.session.userdata,
                    self.quick.config,
                    self.quick.settings,
                    text=text,
                    closing=closing,
                )
            if path == "fast":
                self.fast_for = new_message.id
            if self.prefetcher is not None:
                if turn_ctx is not None and judgement is not None:
                    hook.prefetch = asyncio.ensure_future(
                        self.prefetcher.run(
                            text, judgement, _recent_exchanges(self.session), turn_ctx, new_message
                        )
                    )
                elif judgement is None:
                    # An accepted "hmm" was never judged: nothing to look up.
                    self.prefetcher.cancel()
            if path == "filler" and judgement is not None:
                await self._play_filler(text, judgement, hook, new_message, seen_barge_ins)
            if hook.prefetch is not None:
                # wait() rather than await: a barge-in may have cancelled it.
                await asyncio.wait({hook.prefetch})
            if self._barge_ins != seen_barge_ins:
                self._commit_user_message(new_message)
                _log("dropped_for_barge_in", text)
                raise StopResponse()
        finally:
            hook.done.set()
            if self._hook is hook:
                self._hook = None

    async def _play_filler(
        self,
        text: str,
        judgement: Judgement,
        hook: _Hook,
        new_message: llm.ChatMessage,
        seen_barge_ins: int,
    ) -> None:
        """Says the turn's filler line as soon as it is written while the lookup
        runs: the reply can't start before the lookup is in, so that wait is
        free. Once the lookup is done (or there is none) and the line isn't
        written yet, the reply goes ahead and the line is handed to llm_node
        (with_filler): spoken if it is ready before the reply's first words,
        dropped if not. There is no time limit."""
        assert self.quick is not None
        task = self._filler_task(text, judgement)
        started = self.clock()
        while not task.done():
            prefetch = hook.prefetch
            if prefetch is None or prefetch.done():
                self.pending_filler = _PendingFiller(new_message.id, text, task, started)
                return
            await asyncio.wait({task, prefetch}, return_when=asyncio.FIRST_COMPLETED)
        if task.cancelled() or task.exception() is not None:
            return
        line = task.result()
        if line is None:
            return
        if self._barge_ins != seen_barge_ins:
            # A barge-in took over this turn: its reply is dropped, so is the line.
            _log("filler_skipped", text, filler=line)
            return
        try:
            handle = self.session.say(line, add_to_chat_ctx=False)
        except RuntimeError:
            # Scheduling paused (the session is closing or handing over).
            return
        self._filler_handle = handle
        self._filler_spoken(new_message.id, text, line, self.clock() - started)

    def _filler_spoken(self, message_id: str, text: str, line: str, waited: float) -> None:
        assert self.quick is not None
        self.quick.said.append(line)
        after = self.clock() - self._final_at if self._final_at is not None else None
        _log("filler", text, filler=line, ms=waited * 1000)
        if self.on_filler is not None:
            self.on_filler(line, after, waited)
        if self.on_filler_store is not None:
            self.on_filler_store(message_id, line)

    def with_filler(
        self, stream: AsyncIterable[Any], message_id: str | None, text: str | None = None
    ) -> AsyncIterable[Any]:
        """The reply's stream, with the turn's filler line in front of it when
        the line was still being written as the lookup finished (see
        _play_filler) and is ready before the reply's first words. The reply's
        first words reaching the TTS are the cutoff: a line that is late, or
        that comes in the same moment, is dropped. text: the reply's user
        message, for a barge-in answer, whose filler is keyed on its words."""
        pending = self.pending_filler
        if pending is None or self.quick is None:
            return stream
        if not _is_reply_to(pending.message_id, message_id, text):
            return stream
        if message_id is not None and pending.message_id != message_id:
            pending = replace(pending, message_id=message_id)
        return self._filler_before(stream, pending)

    def is_fast_reply(self, message_id: str | None, text: str | None) -> bool:
        """Whether the reply to this user message is the one routed to the small model."""
        return self.fast_for is not None and _is_reply_to(self.fast_for, message_id, text)

    async def _filler_before(
        self, stream: AsyncIterable[Any], pending: _PendingFiller | None
    ) -> AsyncIterable[Any]:
        it = stream.__aiter__()
        nxt: asyncio.Future | None = None
        try:
            while True:
                nxt = asyncio.ensure_future(it.__anext__())
                while pending is not None and not nxt.done():
                    await asyncio.wait({nxt, pending.task}, return_when=asyncio.FIRST_COMPLETED)
                    if nxt.done():
                        break  # the reply came first, or in the same moment
                    line = _filler_line(pending.task)
                    done, pending, self.pending_filler = pending, None, None
                    if line is None:
                        continue
                    self._filler_segment = True
                    self._filler_spoken(
                        done.message_id, done.text, line, self.clock() - done.started
                    )
                    if self.on_filler_shown is not None:
                        self.on_filler_shown(line)
                    yield line
                    yield FlushSentinel()
                try:
                    chunk = await nxt
                except StopAsyncIteration:
                    return
                if pending is not None and _has_speech(chunk):
                    pending.task.cancel()
                    _log("filler_dropped", pending.text)
                    pending, self.pending_filler = None, None
                yield chunk
        finally:
            if nxt is not None and not nxt.done():
                nxt.cancel()
                await asyncio.gather(nxt, return_exceptions=True)
            if (aclose := getattr(it, "aclose", None)) is not None:
                await aclose()

    def filler_segment(self) -> bool:
        """Whether the segment about to be forwarded is the filler line that
        with_filler put in front of the reply (true once per line)."""
        said, self._filler_segment = self._filler_segment, False
        return said

    def _on_judged(self, text: str, task: asyncio.Task[Judgement]) -> None:
        """Starts the filler as soon as Jev says the turn needs a lookup, so it
        is written while endpointing still runs."""
        if task.cancelled() or task.exception() is not None or self.quick is None:
            return
        judgement = task.result()
        if judgement.p is not None and judgement.p < self.config.thresholds.drop_p:
            return
        route = quick_reply.route(
            judgement, self.session.userdata, self.quick.config, self.quick.settings, text=text
        )
        if route == "filler":
            self._filler_task(text, judgement)

    def _filler_task(self, text: str, judgement: Judgement) -> asyncio.Task[str | None]:
        assert self.quick is not None
        key = turn_gate.normalize(text)
        task = self._fillers.get(key)
        if task is None:
            task = asyncio.ensure_future(
                self.quick.compose(text, judgement.lookup, _recent_exchanges(self.session))
            )
            self._fillers[key] = task
        return task

    def _cancel_fillers(self) -> None:
        for task in self._fillers.values():
            task.cancel()
        self._fillers.clear()
        self.pending_filler = None

    def _filler_playing(self) -> bool:
        handle = self._filler_handle
        if handle is None:
            return False
        if handle.done():
            self._filler_handle = None
            return False
        return True

    def _commit_user_message(self, message: llm.ChatMessage) -> None:
        """Adds a turn whose reply was dropped to the conversation, as the
        library does for a turn it doesn't answer (skip_reply), so the reply that
        replaces it still sees the question -- and the lookups and filler stored
        after it follow it into the transcript. Private API of livekit-agents
        1.7.0, as app.agent.prefetch uses."""
        self.session.current_agent._chat_ctx.items.append(message)
        self.session._conversation_item_added(message)

    async def _after_hook(self) -> None:
        if (hook := self._hook) is not None:
            await hook.done.wait()

    # ---- typed text ----

    async def accepts_typed(self, text: str, message_id: str | None) -> bool:
        """Whether to answer a typed message. Typing is always meant for the
        agent, so only the topic is judged; an off-topic request is ignored like
        an off-topic voice turn and taken off the browser's transcript."""
        if turn_gate.is_sound_only(text):
            return False
        pre = turn_gate.precheck(text, None)
        # Typed text isn't STT output: any script is what the customer wrote.
        userdata = getattr(self.session, "userdata", None)
        if not turn_gate.needs_judge(pre, stt_writes_bengali=False):
            if userdata is not None:
                userdata.wrap_up = closing_offer.acknowledges(text)
            return True
        judgement = await self.judge(text, "listening")
        p = judgement.p
        if p is None or p >= self.config.thresholds.drop_p:
            if userdata is not None:
                userdata.wrap_up = closing_offer.wraps_up(judgement.wrap_up_p, text)
            _log("typed_accept", text, p=p)
            return True
        _log("typed_drop", text, p=p)
        if self.room is not None and message_id:
            try:
                await self.room.local_participant.send_text(
                    json.dumps({"id": message_id, "text": text}), topic=IGNORED_TEXT_TOPIC
                )
            except Exception:
                logger.exception("could not report the ignored typed message")
        return False

    # ---- helpers ----

    def _judge_cached(self, text: str, bot_state: BotState) -> asyncio.Task[Judgement]:
        """Every call is also routed (the lookup question, when the router is on):
        a listening turn is the one the LLM will answer, and a barge-in that
        interrupts the agent gets the same quick reply (see _route_barge_in)."""
        key = f"{bot_state}:{turn_gate.normalize(text)}"
        task = self._judged.get(key)
        if task is None:
            if len(self._judged) > 64:
                self._judged.clear()
            # Over the agent, Jev also hears what it is saying (jev_judge).
            speaking = self._bot_texts[-1] if bot_state != "listening" else ""
            task = asyncio.ensure_future(
                self.judge(text, bot_state, route=True, speaking=speaking)
            )
            self._judged[key] = task
        return task

    async def _publish_user_turn(self, text: str) -> None:
        await publish_user_turn(self.room, text)

    def _gate_reply(self, text: str) -> None:
        if self.on_gate_reply is not None:
            self.on_gate_reply(text)

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("turn gate task failed", exc_info=exc)


async def publish_user_turn(room: rtc.Room | None, text: str) -> None:
    """Sends a voice turn the agent is answering to the browser (USER_TURN_TOPIC)."""
    if room is None:
        return
    try:
        await room.local_participant.send_text(json.dumps({"text": text}), topic=USER_TURN_TOPIC)
    except Exception:
        logger.exception("could not publish the accepted user turn")


def _last_user(chat_ctx: llm.ChatContext) -> tuple[str | None, str | None]:
    """(id, text) of the conversation's last user message."""
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and item.role == "user":
            return item.id, item.text_content
    return None, None


def _text_key(text: str) -> str:
    return "text:" + turn_gate.normalize(text)


def _is_reply_to(key: str, message_id: str | None, text: str | None) -> bool:
    """Whether a route's key (a user message id, or _text_key for a barge-in
    answer, whose user message doesn't exist yet) belongs to this reply."""
    return key == message_id or (text is not None and key == _text_key(text))


def _filler_line(task: asyncio.Task[str | None]) -> str | None:
    """The finished filler task's line; None if it failed, was cancelled or wrote none."""
    if task.cancelled() or task.exception() is not None:
        return None
    return task.result()


def _has_speech(chunk: Any) -> bool:
    """Whether a reply-stream item carries words for the TTS (not a tool call)."""
    if isinstance(chunk, str):
        return bool(chunk.strip())
    if isinstance(chunk, llm.ChatChunk) and chunk.delta is not None:
        return bool((chunk.delta.content or "").strip())
    return False


def _bot_state(agent_state: str) -> BotState:
    return "speaking" if agent_state == "speaking" else "thinking"


def _log(decision: str, text: str, **extra) -> None:
    pre = extra.pop("pre", None)
    if pre is not None:
        extra.update(script=pre.script, words=pre.word_count, confidence=pre.confidence)
    if (ms := extra.get("ms")) is not None:
        extra["ms"] = round(ms)
    logger.info("turn gate %s: %r %s", decision, text, extra)


def _userdata(agent: Agent) -> Any:
    """The session's SessionUserdata, or None when the agent isn't running in a
    session (tests)."""
    try:
        return agent.session.userdata
    except (RuntimeError, ValueError):
        return None


class GatedAgent(Agent):
    """An Agent whose voice turns go through a TurnGateController."""

    def __init__(self, *, gate: TurnGateController, **kwargs) -> None:
        super().__init__(**kwargs)
        self._gate = gate

    def on_greeting_done(self) -> None:
        self._gate.reset()

    @property
    def prefetcher(self) -> Prefetcher | None:
        return self._gate.prefetcher

    @property
    def gate(self) -> TurnGateController:
        return self._gate

    def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings
    ) -> AsyncIterable[llm.ChatChunk | str]:
        message_id, text = _last_user(chat_ctx)
        reply = reply_punctuation.clean_reply_stream(self._reply(chat_ctx, tools, model_settings))
        return self._gate.with_filler(reply, message_id, text)

    async def _reply(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings
    ) -> AsyncIterable[llm.ChatChunk | str]:
        """The small model answers the turn the gate routed to it (fast_for);
        when it hands off, and for every other reply and tool step, the main
        model does. Matching the reply's own user message means a route never
        carries over to a later reply (a barge-in, a queued answer)."""
        gate = self._gate
        quick = gate.quick
        fast = gate.is_fast_reply(*_last_user(chat_ctx))
        if quick is not None and fast:
            gate.fast_for = None
            fast_llm = quick.fast_llm()
            self._forward_metrics(fast_llm)
            model = quick.config.quick_reply_model
            if quick.on_event is not None:
                quick.on_event(f"fast answer: asking {model}")
            said: list[str] = []
            try:
                async for chunk in quick_reply.stream_fast(
                    fast_llm,
                    quick_reply.fast_chat_ctx(chat_ctx),
                    quick_reply.end_call_tools(tools),
                    buffer_chars=quick.settings.fast_buffer_chars,
                    first_chunk_timeout_s=quick.settings.fast_timeout_ms / 1000,
                ):
                    if isinstance(chunk, str):
                        said.append(chunk)
                    elif chunk.delta is not None and chunk.delta.content:
                        said.append(chunk.delta.content)
                    yield chunk
            except quick_reply.Handoff:
                _log("fast_handoff", "")
                if quick.on_event is not None:
                    quick.on_event(f"fast answer: {model} passed it to the main model")
                if gate.on_fast is not None:
                    gate.on_fast(True)
            else:
                if quick.on_event is not None:
                    quick.on_event(f'fast answer: {model} said "{"".join(said).strip()}"')
                if gate.on_fast is not None:
                    gate.on_fast(False)
                return
        async for chunk in self._cards_with_speech(
            Agent.default.llm_node(
                self, closing_offer.with_reminder(chat_ctx, _userdata(self)), tools, model_settings
            )
        ):
            yield chunk

    async def _cards_with_speech(self, stream: AsyncIterable[Any]) -> AsyncIterable[Any]:
        """The main model's stream, with a pending card put on the
        customer's screen as its first words come (the reply starts being
        transcribed and spoken), not while a filler line or the lookup is still
        going (see userdata.defer_cards). A step that ends without words and
        without a tool call is the last one: the cards go then."""
        userdata = _userdata(self)
        tool_call = False
        try:
            async for chunk in stream:
                if userdata is not None and userdata.pending_card is not None:
                    if _has_speech(chunk):
                        await cards.flush_pending_card(userdata)
                if isinstance(chunk, llm.ChatChunk) and chunk.delta is not None and chunk.delta.tool_calls:
                    tool_call = True
                yield chunk
        except Exception as exc:
            logger.exception("main model stream failed: %s; saying a fallback line", exc)
            yield STREAM_FAILED_LINE
            return
        if userdata is not None and not tool_call and userdata.pending_card is not None:
            await cards.flush_pending_card(userdata)

    def _forward_metrics(self, fast_llm: llm.LLM) -> None:
        """The small model's metrics go where the main model's do (timing log,
        usage totals): the activity only listens to its own LLM. Private API of
        livekit-agents 1.7.0 (AgentActivity._on_metrics_collected)."""
        if getattr(self, "_metrics_forwarded_to", None) is fast_llm:
            return
        try:
            activity = self._get_activity_or_raise()
        except RuntimeError:
            return
        fast_llm.on("metrics_collected", activity._on_metrics_collected)
        self._metrics_forwarded_to = fast_llm

    async def accepts_typed(self, text: str, message_id: str | None) -> bool:
        return await self._gate.accepts_typed(text, message_id)

    def release_pause(self) -> None:
        self._gate.release_pause()

    def stt_node(self, audio: AsyncIterable[rtc.AudioFrame], model_settings):
        # The mic audio the STT hears also gives the gate its level.
        return Agent.default.stt_node(self, self._metered(audio), model_settings)

    async def _metered(self, audio: AsyncIterable[rtc.AudioFrame]) -> AsyncIterable[rtc.AudioFrame]:
        """Every frame's level goes to the gate. With voice isolation on, a frame
        under the bar (the floor, or the caller's level less the margin) reaches
        the VAD and STT as silence, so room chatter never becomes a transcript;
        the hangover keeps soft word endings and short gaps between words."""
        config = self._gate.config
        hangover_until = 0.0
        async for frame in audio:
            samples = np.frombuffer(frame.data, dtype=np.int16)
            db = voice_level.dbfs(samples)
            self._gate.on_audio_level(db, frame.samples_per_channel / frame.sample_rate)
            if not config.voice_isolation_enabled:
                yield frame
                continue
            ref = self._gate.caller_reference
            cutoff = config.speech_floor_dbfs
            if ref is not None:
                cutoff = max(cutoff, ref - config.speech_margin_db)
            now = self._gate.clock()
            if db >= cutoff:
                hangover_until = now + _ISOLATION_HANGOVER_S
                yield frame
            elif now < hangover_until:
                yield frame
            else:
                yield rtc.AudioFrame(
                    data=b"\x00" * (frame.num_channels * frame.samples_per_channel * 2),
                    sample_rate=frame.sample_rate,
                    num_channels=frame.num_channels,
                    samples_per_channel=frame.samples_per_channel,
                )

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        try:
            await self._gate.on_user_turn_completed(new_message, turn_ctx)
        except StopResponse:
            raise
        except Exception as exc:
            logger.exception("Unexpected error in GatedAgent.on_user_turn_completed: %s", exc)
            try:
                self.session.say(STREAM_FAILED_LINE, add_to_chat_ctx=True)
            except Exception:
                pass
            raise StopResponse()

    async def transcription_node(
        self, text: AsyncIterable[str | Any], model_settings
    ) -> AsyncIterable[str | Any]:
        # Items pass through unchanged: TimedString timing drives transcript sync.
        self._gate.bot_reply_started()
        if self._gate.filler_segment():
            # The filler line the gate put in front of the reply: heard, so the
            # echo check knows it, but not part of what the agent said in the
            # chat context (the transcript stores it, see on_filler_store).
            async for delta in text:
                self._gate.bot_said(str(delta))
            return
        async for delta in text:
            self._gate.bot_said(str(delta))
            yield delta


class TurnPublishingAgent(Agent):
    """The ungated agent: every voice turn it answers is published on
    USER_TURN_TOPIC, as the gate does for the turns it accepts (phone calls have
    no room, so nothing is published), and non-speech tags are dropped.

    on_user_turn_completed (livekit-agents 1.7, AgentActivity._user_turn_completed_task)
    runs only for a turn that gets a reply: turns skipped because the reply was
    skipped, the current speech can't be interrupted (e.g. the greeting) or
    scheduling is paused return before it, and a reply is generated right after
    it. Typed chat doesn't come through here; the browser shows it as sent."""

    def __init__(self, *, room: rtc.Room | None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._room = room

    def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings
    ) -> AsyncIterable[llm.ChatChunk | str]:
        return reply_punctuation.clean_reply_stream(
            Agent.default.llm_node(
                self, closing_offer.with_reminder(chat_ctx, _userdata(self)), tools, model_settings
            )
        )

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        text = (new_message.text_content or "").strip()
        if turn_gate.is_sound_only(text):
            # "[clears throat]": the STT heard a sound, not a request.
            raise StopResponse()
        # A phone number said as words reaches the agent as digits: the LLM
        # miscounts "double"/"triple" when it writes them itself.
        if (digits := spoken_digits_in_text(text)) != text:
            text = digits
            new_message.content = [text]
        if text:
            await publish_user_turn(self._room, text)


async def _text_input_cb(session: AgentSession, ev: room_io.TextInputEvent) -> None:
    # Used by every browser session, gated or not. Text sent before the greeting
    # has played out is dropped (the browser also keeps Send disabled until then).
    if not session.userdata.greeting_done:
        return
    # Judged before the interrupt, so an off-topic message doesn't cut the agent off.
    agent = session.current_agent
    if isinstance(agent, GatedAgent):
        # stream_id is the browser's chat message id (the JS SDK's TextStreamInfo.id).
        message_id = ev.info.stream_id if ev.info is not None else None
        if not await agent.accepts_typed(ev.text, message_id):
            return
    # Mirrors livekit's default text_input_cb (voice/room_io/types.py), relying on
    # its private _claim_user_turn, but forces the interrupt: with interruption
    # off every reply is uninterruptible, and a plain interrupt() would raise.
    async with session._claim_user_turn():
        await session.interrupt(force=True)
        if isinstance(agent, GatedAgent):
            agent.release_pause()
        session.generate_reply(user_input=ev.text)


def room_options() -> room_io.RoomOptions:
    return room_io.RoomOptions(text_input=room_io.TextInputOptions(text_input_cb=_text_input_cb))
