"""Asks a quiet customer whether they need anything else, and ends the call if
they don't.

Quiet means no turn reached the conversation. The turn gate drops background
speech and noise without adding it to the chat, so only the customer's own
questions, spoken or typed, restart the clock. The clock runs only while the
agent is listening: a long answer doesn't use it up.

After `idle_s` of that, the agent asks (IDLE_CHECKIN_LINES). A customer who
says they're done gets the LLM's goodbye, and end_call after it (see
entrypoint._session_tools). Anything they ask is answered as usual and the
clock starts over. With no turn at all within `grace_s`, the agent says
goodbye (IDLE_GOODBYE_LINES) and the call ends.
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable

from livekit.agents import AgentSession

from app.agent.prompt_defaults import IDLE_CHECKIN_LINES, IDLE_GOODBYE_LINES

logger = logging.getLogger("agent.idle_checkin")

_BENGALI_RE = re.compile("[ঀ-৲৴-৿]")


def _reply_language(session: AgentSession) -> str:
    """The language of the agent's last reply; Bangla, the default, when none."""
    for item in reversed(session.history.items):
        if getattr(item, "role", None) == "assistant" and (text := item.text_content):
            return "bn" if _BENGALI_RE.search(text) else "en"
    return "bn"


class IdleCheckIn:
    """Attach, then call start() once the greeting has played out."""

    def __init__(
        self,
        *,
        session: AgentSession,
        on_end: Callable[[], Awaitable[None]],
        idle_s: float,
        grace_s: float,
    ) -> None:
        self.session = session
        self._on_end = on_end
        self.idle_s = idle_s
        self.grace_s = grace_s
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
        logger.info("customer idle for %.0fs, checking in", self.idle_s)
        self._asked = True
        self.session.say(IDLE_CHECKIN_LINES[_reply_language(self.session)])

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
