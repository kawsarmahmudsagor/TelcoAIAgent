"""Asks a quiet customer whether they need anything else, and ends the call if
they don't.

Quiet means no turn reached the conversation. The turn gate drops background
speech and noise without adding it to the chat, so only the customer's own
questions, spoken or typed, restart the clock. The clock runs only while the
agent is listening: a long answer doesn't use it up.

After `idle_s` of that, the agent checks in with a line that follows the
conversation: the quick-reply model writes it (compose_check_in) when the
session has an OpenRouter connection, else check_in_line picks one -- the code
a recharge or purchase is waiting for, the complaint being drafted, the
agent's last question, or IDLE_CHECKIN_LINES. A customer who says they're done
gets the LLM's goodbye, and end_call after it (see entrypoint._session_tools).
Anything they ask is answered as usual and the clock starts over. With no turn
at all within `grace_s`, the agent says goodbye (IDLE_GOODBYE_LINES) and the
call ends. Nothing is said while the customer is speaking.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable

import httpx
from livekit.agents import AgentSession

from app.agent.prompt_defaults import IDLE_CHECKIN_LINES, IDLE_GOODBYE_LINES
from app.agent.quick_models import reasoning_for

logger = logging.getLogger("agent.idle_checkin")

_BENGALI_RE = re.compile("[ঀ-৲৴-৿]")
_HISTORY = 6
# Asked again this much later when the customer is mid-sentence at check-in time.
_SPEAKING_RETRY_S = 2.0
_CHECK_IN_MAX_WORDS = 16

_CHECK_IN_SYSTEM = """You write the short line a mobile operator's phone assistant says aloud when \
the customer has gone quiet.
Write one short, polite, natural spoken question (under 12 words) that checks in and helps the \
conversation move on, based on the RECENT conversation:
- A recharge, pack purchase or offer is waiting for the code sent to their phone: ask for the code.
- A complaint is being written up: ask whether to go ahead with it.
- The assistant's last message already offered more help: ask whether they're still there.
- The assistant just asked a question or offered a choice: follow up on exactly that.
- A balance, usage or pack answer was just given: ask whether they need anything else about it.
- Little was said yet: ask how you can help with their mobile service.
Language: the language of the conversation. Bangla in Bengali script, in the respectful আপনি form, \
the way people actually speak, with the English words Bangla speakers use (চেক, প্যাক, ব্যালেন্স, \
কোড); you may open with "আপনি কি আছেন?". English: everyday spoken English.
Never repeat the assistant's last message. Never state a balance, price, amount, code or any other \
number, and never promise anything.
Reply with JSON only: {"text": "..."}"""


def _reply_language(session: AgentSession) -> str:
    """The language of the agent's last reply; Bangla, the default, when none."""
    for item in reversed(session.history.items):
        if getattr(item, "role", None) == "assistant" and (text := item.text_content):
            return "bn" if _BENGALI_RE.search(text) else "en"
    return "bn"


def _recent_exchanges(session: AgentSession) -> list[tuple[str, str]]:
    """The last (role, text) messages of the conversation."""
    out: list[tuple[str, str]] = []
    for item in session.history.items:
        if getattr(item, "type", None) != "message" or item.role not in ("user", "assistant"):
            continue
        if text := item.text_content:
            out.append((item.role, text))
    return out[-_HISTORY:]


def _waiting_for(userdata: object) -> str | None:
    """What the call is waiting on the customer for, if anything."""
    action = getattr(userdata, "pending_action", None)
    if action is not None:
        kind = getattr(action.kind, "value", action.kind)
        return f"a {kind} waiting for the code sent to the customer's phone"
    if getattr(userdata, "pending_case", None) is not None:
        return "a complaint being written up, waiting for the customer's go-ahead"
    return None


def check_in_line(session: AgentSession) -> str:
    """The check-in without a model: what the call is waiting for, the agent's
    last question, or the plain IDLE_CHECKIN_LINES."""
    lang = _reply_language(session)
    bn = lang == "bn"
    userdata = getattr(session, "userdata", None)
    if getattr(userdata, "pending_action", None) is not None:
        return (
            "আপনি কি আছেন? ফোনে যে কোডটা গেছে, ওটা বলবেন?"
            if bn
            else "Are you still there? Could you tell me the code sent to your phone?"
        )
    if getattr(userdata, "pending_case", None) is not None:
        return (
            "আপনি কি আছেন? কমপ্লেইনটা সাবমিট করে দেবো?"
            if bn
            else "Are you still there? Shall I go ahead with the complaint?"
        )
    last = _recent_exchanges(session)[-1:]
    if last and last[0][0] == "assistant" and last[0][1].rstrip().endswith(("?", "？")):
        return (
            "আপনি কি আছেন? আগের ব্যাপারটা নিয়ে কী ভাবলেন?"
            if bn
            else "Are you still there? Let me know what you think about that."
        )
    return IDLE_CHECKIN_LINES[lang]


async def compose_check_in(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    history: list[tuple[str, str]],
    waiting_for: str | None = None,
    *,
    timeout_s: float = 2.5,
) -> str | None:
    """A check-in line written for this conversation, or None on any error,
    timeout or unusable line (too long, or with a number in it)."""
    lines = ["Recent conversation:"]
    lines += [f"{'Customer' if role == 'user' else 'Assistant'}: {text}" for role, text in history]
    if not history:
        lines.append("(the call just started)")
    if waiting_for:
        lines.append(f"Waiting for: {waiting_for}.")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _CHECK_IN_SYSTEM},
            {"role": "user", "content": "\n".join(lines)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": 80,
        "reasoning": reasoning_for(model),
        # Customer speech: keep it out of provider training data.
        "provider": {"sort": "latency", "data_collection": "deny"},
    }
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            ),
            timeout_s,
        )
        response.raise_for_status()
        text = json.loads(response.json()["choices"][0]["message"]["content"])["text"]
    except (TimeoutError, asyncio.TimeoutError):
        logger.info("check-in line timed out after %.2fs", timeout_s)
        return None
    except Exception as exc:
        logger.warning("check-in line failed: %s", exc)
        return None
    text = " ".join(text.split()) if isinstance(text, str) else ""
    if not text or len(text.split()) > _CHECK_IN_MAX_WORDS or re.search(r"\d", text):
        logger.info("check-in line dropped: %r", text)
        return None
    logger.info("check-in line by %s in %.2fs: %r", model, time.perf_counter() - started, text)
    return text


class IdleCheckIn:
    """Attach, then call start() once the greeting has played out. With client,
    model and api_key the check-in line is written for the conversation."""

    def __init__(
        self,
        *,
        session: AgentSession,
        on_end: Callable[[], Awaitable[None]],
        idle_s: float,
        grace_s: float,
        client: httpx.AsyncClient | None = None,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self.session = session
        self._on_end = on_end
        self.idle_s = idle_s
        self.grace_s = grace_s
        self.client = client
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self._started = False
        self._asked = False
        self._timer: asyncio.TimerHandle | None = None
        self._tasks: set[asyncio.Task] = set()

    def attach(self) -> None:
        self.session.on("conversation_item_added", self._on_item)
        self.session.on("agent_state_changed", self._on_agent_state)
        self.session.on("close", lambda _ev: self._cancel())

    def start(self) -> None:
        self._started = True
        self._arm(self.idle_s)

    def _on_item(self, ev) -> None:
        if not self._started or getattr(ev.item, "role", None) != "user":
            return
        # The customer answered: the LLM handles it, and the clock restarts in
        # case no reply follows.
        self._asked = False
        self._arm(self.idle_s)

    def _on_agent_state(self, ev) -> None:
        if not self._started:
            return
        if ev.new_state in ("thinking", "speaking"):
            self._cancel()
        elif ev.new_state == "listening":
            self._arm(self.grace_s if self._asked else self.idle_s)

    def _arm(self, delay: float) -> None:
        self._cancel()
        self._timer = asyncio.get_running_loop().call_later(delay, self._fire)

    def _cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _fire(self) -> None:
        self._timer = None
        self._spawn(self._end() if self._asked else self._check_in())

    async def _check_in(self) -> None:
        if self.session.user_state == "speaking":
            self._arm(_SPEAKING_RETRY_S)
            return
        logger.info("customer idle for %.0fs, checking in", self.idle_s)
        self._asked = True
        line = None
        if self.client is not None and self.model and self.api_key:
            line = await compose_check_in(
                self.client,
                self.base_url,
                self.api_key,
                self.model,
                _recent_exchanges(self.session),
                _waiting_for(getattr(self.session, "userdata", None)),
            )
        # The customer may have spoken, or the call ended, while it was written.
        if not self._started or not self._asked:
            return
        if self.session.user_state == "speaking":
            self._asked = False
            self._arm(_SPEAKING_RETRY_S)
            return
        self.session.say(line or check_in_line(self.session))

    async def _end(self) -> None:
        logger.info("no answer to the check-in in %.0fs, ending the call", self.grace_s)
        self._started = False
        try:
            handle = self.session.say(
                IDLE_GOODBYE_LINES[_reply_language(self.session)], allow_interruptions=False
            )
            await handle.wait_for_playout()
        finally:
            await self._on_end()

    def _spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("idle check-in failed", exc_info=exc)
