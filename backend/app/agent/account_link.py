"""Upgrades a guest browser session to the customer who logs in during it, so
the conversation carries on instead of starting over.

The browser can't do this itself. After the login, the Next.js route
/api/assistant/link checks the portal_session cookie with FastAPI and writes
{"subscriber_id": ...} into the room's metadata through the LiveKit server
API; participant tokens carry no roomAdmin grant, so only the server can set
room metadata. The agent then takes the account: the snapshot in the prompt,
the customer's name, the conversation row, and the tools (each one reads
userdata.subscriber_id when it's called). It answers on from there.

Only a guest is ever upgraded. A session that already belongs to a customer
ignores the metadata; the browser ends it on logout or a switch of customer,
and ACCOUNT_ATTRIBUTE tells it whose session it is.
"""

import asyncio
import json
import logging
import uuid

from livekit import rtc
from livekit.agents import Agent, AgentSession

from app.agent import voice_mode
from app.agent.prompt_defaults import LOGIN_FOLLOWUP
from app.agent.session_context import parse_uuid
from app.agent.snapshot import GUEST_SNAPSHOT, load_session_context
from app.agent.userdata import SessionUserdata
from app.db.session import SessionLocal
from app.repositories import conversation_repo
from app.services.agent_config_service import ResolvedAgentConfig

logger = logging.getLogger("agent.account_link")

# The agent's participant attribute: the session's subscriber id, "" for a guest.
# Must match ACCOUNT_ATTRIBUTE in frontend/components/customer/account-link.tsx.
ACCOUNT_ATTRIBUTE = "account"


def parse_link(metadata: str | None) -> uuid.UUID | None:
    """The subscriber id the server put in the room metadata, if any."""
    try:
        meta = json.loads(metadata) if metadata else None
    except json.JSONDecodeError:
        return None
    return parse_uuid(meta.get("subscriber_id")) if isinstance(meta, dict) else None


async def publish_account(room: rtc.Room, userdata: SessionUserdata) -> None:
    sid = userdata.subscriber_id
    await room.local_participant.set_attributes({ACCOUNT_ATTRIBUTE: str(sid) if sid else ""})


def _link_conversation(conversation_id: uuid.UUID, subscriber_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        conversation_repo.link_subscriber(db, conversation_id, subscriber_id)
    finally:
        db.close()


class AccountLink:
    """Attach once the session is running (browser sessions only)."""

    def __init__(
        self,
        *,
        session: AgentSession,
        agent: Agent,
        userdata: SessionUserdata,
        room: rtc.Room,
        config: ResolvedAgentConfig,
    ) -> None:
        self.session = session
        self.agent = agent
        self.userdata = userdata
        self.room = room
        # The session's start-time config: a dashboard change applies to new sessions only.
        self.config = config
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    def attach(self) -> None:
        self.room.on("room_metadata_changed", self._on_metadata)

    def _on_metadata(self, _old: str, new: str) -> None:
        if (subscriber_id := parse_link(new)) is None:
            return
        task = asyncio.ensure_future(self.link(subscriber_id))
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    async def link(self, subscriber_id: uuid.UUID) -> bool:
        """Takes the account if this is still a guest session. True when it did."""
        async with self._lock:
            if self.userdata.subscriber_id is not None:
                if self.userdata.subscriber_id != subscriber_id:
                    logger.warning("ignoring a link to another account on a customer session")
                return False
            ctx = await asyncio.to_thread(load_session_context, subscriber_id, None)
            if ctx.subscriber_id is None:
                logger.warning("ignoring a link to an unknown subscriber")
                return False
            old = self.userdata.snapshot_text or GUEST_SNAPSHOT
            instructions = self.agent.instructions
            if old in instructions:
                await self.agent.update_instructions(instructions.replace(old, ctx.snapshot, 1))
            self.userdata.subscriber_id = ctx.subscriber_id
            self.userdata.customer_name = ctx.customer_name
            self.userdata.snapshot_text = ctx.snapshot
            if (conversation_id := self.userdata.conversation_id) is not None:
                await asyncio.to_thread(_link_conversation, conversation_id, ctx.subscriber_id)
            await publish_account(self.room, self.userdata)
            try:
                # The guest's text-only mode gives way to the customer's: the mic opens.
                await voice_mode.apply(
                    self.session, self.agent, self.userdata, self.config, self.room
                )
            except Exception:
                logger.exception("could not switch the voice mode; the session stays text-only")
            logger.info("guest session linked to the customer who logged in")
            self.session.generate_reply(instructions=LOGIN_FOLLOWUP)
            return True

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            logger.error("account link failed", exc_info=exc)
