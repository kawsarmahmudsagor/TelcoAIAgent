"""end_call for browser calls: the goodbye first, then the browser ends the call.

The model says its goodbye and calls end_call in the same reply. The tool waits
until that goodbye has played, then asks the browser over RPC to end the call
the way its End call button does (frontend hooks/useAgentEndCall.ts), so the
call screen closes normally instead of the room being deleted under it.

A model that calls end_call with no goodbye before it gets one asked for in the
tool's result, and the browser is told once that reply has played. Should the
browser never end the call (tab closed, RPC lost), the agent deletes the room
after FALLBACK_S.

Phone calls keep the library's EndCallTool: there is no browser to ask.
"""

import asyncio
import logging

from livekit.agents import AgentSession, RunContext, function_tool, get_job_context
from livekit.agents.llm import FunctionTool
from livekit.agents.voice.speech_handle import SpeechHandle

logger = logging.getLogger("agent.browser_end_call")

# Must match END_CALL_RPC in frontend/hooks/useAgentEndCall.ts.
END_CALL_RPC = "end_call"
FALLBACK_S = 120.0
_RPC_TIMEOUT_S = 5.0

_DESCRIPTION = """
Ends the call. Say your goodbye first, then call this in the same reply: the call ends once
the goodbye has played. Nothing more can be said after it.
"""


def _said_before(ctx: RunContext) -> bool:
    """Whether this tool call's own reply said something before it. The reply's
    message has the generation's id; its function calls are "<that id>/fnc_N"."""
    generation_id = ctx.function_call.id.rpartition("/fnc_")[0]
    return any(
        item.type == "message"
        and item.role == "assistant"
        and item.id == generation_id
        and not item.interrupted
        and (item.text_content or "").strip()
        for item in ctx.speech_handle.chat_items
    )


class BrowserEndCall:
    """Per session: it remembers that the call is ending, so a second end_call
    (the model calling it again from the goodbye it was asked for) does nothing."""

    def __init__(
        self, *, goodbye_instructions: str, extra_description: str = "", fallback_s: float = FALLBACK_S
    ):
        self._goodbye_instructions = goodbye_instructions
        self._fallback_s = fallback_s
        self._ending = False
        self._fallback: asyncio.Task[None] | None = None
        self.tool: FunctionTool = function_tool(
            self._end_call,
            name="end_call",
            description=f"{_DESCRIPTION}\n{extra_description}",
        )

    async def _end_call(self, ctx: RunContext) -> str | None:
        if self._ending:
            return None
        # A goodbye interrupted by the customer cancels this tool, and the call goes on.
        await ctx.wait_for_playout()
        self._ending = True
        session = ctx.session
        if _said_before(ctx):
            await self._ask_browser(session)
            return None

        def _on_reply_done(handle: SpeechHandle) -> None:
            if handle.interrupted:
                self._ending = False
                return
            asyncio.create_task(self._ask_browser(session))

        # The goodbye asked for below is spoken under the same speech handle.
        ctx.speech_handle.add_done_callback(_on_reply_done)
        return self._goodbye_instructions

    async def _ask_browser(self, session: AgentSession) -> None:
        if self._fallback is None:
            self._fallback = asyncio.create_task(self._end_anyway())
            session.once("close", lambda _: self._fallback and self._fallback.cancel())
        try:
            room_io = session.room_io
            caller = room_io.linked_participant
            if caller is None:
                raise RuntimeError("no caller linked to the session")
            await room_io.room.local_participant.perform_rpc(
                destination_identity=caller.identity,
                method=END_CALL_RPC,
                payload="",
                response_timeout=_RPC_TIMEOUT_S,
            )
            logger.info("asked the browser to end the call")
        except Exception:
            logger.warning(
                "couldn't ask the browser to end the call; ending it in %.0f s",
                self._fallback_s,
                exc_info=True,
            )

    async def _end_anyway(self) -> None:
        await asyncio.sleep(self._fallback_s)
        logger.warning("the browser didn't end the call; deleting the room")
        job = get_job_context()
        await job.delete_room()
        job.shutdown(reason="browser did not end the call")
