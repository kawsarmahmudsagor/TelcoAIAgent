"""The confirm card's RPC methods (browser sessions only): Confirm / Cancel
call `telco.confirm_action` / `telco.cancel_action` on the agent. Each answers
quickly with JSON {ok, error} -- performRpc gives up after 15 s -- and never
raises. The result is spoken by the session afterwards."""

import asyncio
import json
import logging
from collections.abc import Callable
from uuid import UUID

from livekit import rtc

from app.agent import actions
from app.agent.tools._common import error_text
from app.agent.topics import RPC_CANCEL, RPC_CONFIRM
from app.agent.userdata import SessionUserdata
from app.bss.errors import BssError

logger = logging.getLogger("agent.action_rpc")


def _reply(ok: bool, error: str | None = None) -> str:
    return json.dumps({"ok": ok, "error": error})


class ActionRpc:
    def __init__(
        self,
        session,
        userdata: SessionUserdata,
        room: rtc.Room,
        linked_identity: Callable[[], str | None],
    ) -> None:
        self._session = session
        self._userdata = userdata
        self._room = room
        self._linked_identity = linked_identity
        self._tasks: set[asyncio.Task] = set()

    def register(self) -> None:
        participant = self._room.local_participant
        participant.register_rpc_method(RPC_CONFIRM, self.confirm)
        participant.register_rpc_method(RPC_CANCEL, self.cancel)

    async def confirm(self, data: rtc.RpcInvocationData) -> str:
        return await self._handle(data, self._confirm)

    async def cancel(self, data: rtc.RpcInvocationData) -> str:
        return await self._handle(data, self._cancel)

    async def settle(self) -> None:
        """Waits for the spoken follow-ups to be requested (tests)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _handle(self, data: rtc.RpcInvocationData, handler) -> str:
        if data.caller_identity != self._linked_identity():
            return _reply(False, "Not allowed.")
        try:
            payload = json.loads(data.payload)
            action_id = UUID(str(payload["action_id"]))
        except (TypeError, ValueError, KeyError):
            return _reply(False, "Bad request.")
        try:
            return await handler(action_id, payload)
        except BssError as exc:
            text = error_text(exc)
            self._say(f"The customer used the confirm card, but it didn't go through. {text}")
            return _reply(False, text)
        except Exception:
            logger.exception("confirm card RPC failed")
            self._say(
                "The customer used the confirm card, but something went wrong on our side. "
                "Apologise in one short line and ask them to try again."
            )
            return _reply(False, "internal")

    def _say(self, instructions: str) -> None:
        # Not awaited: the reply plays after the RPC has answered.
        try:
            self._session.generate_reply(instructions=instructions)
        except RuntimeError:
            logger.warning("session closed; confirm card reply dropped")

    def _already_done(self, action_id: UUID) -> bool:
        ud = self._userdata
        done = ud.done_action
        return done is not None and done[0] == action_id and ud.pending_action is None

    async def _confirm(self, action_id: UUID, payload: dict) -> str:
        if self._already_done(action_id):
            # A replayed confirm: the result was already spoken.
            return _reply(True)
        text = await actions.confirm_action(
            self._userdata, str(payload.get("code") or ""), action_id=action_id
        )
        self._say(
            f"The customer confirmed on the card. {text} Tell them briefly it's done."
        )
        return _reply(True)

    async def _cancel(self, action_id: UUID, payload: dict) -> str:
        text = await actions.cancel_action(self._userdata, action_id=action_id)
        self._say(f"The customer cancelled on the card. {text} Acknowledge briefly.")
        return _reply(True)
