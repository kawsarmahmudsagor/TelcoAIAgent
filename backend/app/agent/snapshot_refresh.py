"""Keeps the system prompt's ACCOUNT SNAPSHOT in step with the database during
a session, without ever making a reply wait for it.

The snapshot is re-read in a worker thread when the agent finishes a reply
(its own purchase or recharge has just landed), when the customer starts
speaking (the read is done long before their turn ends), and every
`interval_s` while the agent is listening (an admin change, a pending recharge
applied, a change made in another tab). One read runs at a time; a trigger
during it is dropped, the next one catches up.

Only a changed snapshot is swapped in, and only its text: the rest of the
instructions, current date included, stay byte-identical, so the LLM
provider's prompt cache keeps hitting on the prefix before it.
"""

import asyncio
import logging

from livekit.agents import Agent, AgentSession

from app.agent.snapshot import load_snapshot
from app.agent.userdata import SessionUserdata

logger = logging.getLogger("agent.snapshot_refresh")


class SnapshotRefresher:
    """Attach, then start() once the session is running. Logged-in sessions only."""

    def __init__(
        self,
        *,
        session: AgentSession,
        agent: Agent,
        userdata: SessionUserdata,
        interval_s: float,
    ) -> None:
        self.session = session
        self.agent = agent
        self.userdata = userdata
        self.interval_s = interval_s
        self._started = False
        self._task: asyncio.Task | None = None
        self._timer: asyncio.TimerHandle | None = None

    def attach(self) -> None:
        self.session.on("agent_state_changed", self._on_agent_state)
        self.session.on("user_state_changed", self._on_user_state)
        self.session.on("close", lambda _ev: self._stop())

    def start(self) -> None:
        self._started = True
        self._arm()

    def refresh(self) -> None:
        """Starts a background re-read unless one is already running."""
        if not self._started or self.userdata.subscriber_id is None:
            return
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.ensure_future(self._run())
        self._task.add_done_callback(self._task_done)

    def _on_agent_state(self, ev) -> None:
        if ev.new_state == "listening":
            self.refresh()

    def _on_user_state(self, ev) -> None:
        if ev.new_state == "speaking":
            self.refresh()

    def _arm(self) -> None:
        if self.interval_s > 0 and self._started:
            self._timer = asyncio.get_running_loop().call_later(self.interval_s, self._tick)

    def _tick(self) -> None:
        self._timer = None
        if self.session.agent_state == "listening":
            self.refresh()
        self._arm()

    def _stop(self) -> None:
        self._started = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._task is not None:
            self._task.cancel()

    async def _run(self) -> None:
        subscriber_id = self.userdata.subscriber_id
        if subscriber_id is None:
            return
        fresh = await asyncio.to_thread(load_snapshot, subscriber_id)
        old = self.userdata.snapshot_text
        if fresh is None or old is None or fresh == old or not self._started:
            return
        instructions = self.agent.instructions
        if old not in instructions:
            # A customised prompt that dropped the snapshot: nothing to update.
            return
        await self.agent.update_instructions(instructions.replace(old, fresh, 1))
        self.userdata.snapshot_text = fresh
        logger.info("account snapshot refreshed")

    def _task_done(self, task: asyncio.Task) -> None:
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("snapshot refresh failed", exc_info=exc)
