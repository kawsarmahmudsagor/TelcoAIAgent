"""end_call for browser sessions: the goodbye first, then the browser turns the mic off.

A browser session is one conversation that can switch between text and voice, so
ending the voice part never closes the room: the chat stays open and the customer
can type, or turn the mic on again. The model says its goodbye and calls end_call
in the same reply. The tool waits until that goodbye has played, then asks the
browser over RPC to turn the mic off (frontend hooks/useAgentEndCall.ts).

A model that calls end_call with no goodbye before it gets one asked for in the
tool's result, and the browser is told once that reply has played. Should the
RPC fail (tab closed), nothing more happens: the room ends when the browser leaves.

Phone calls keep the library's EndCallTool: there is no browser to ask.
"""

import asyncio
import logging

from livekit.agents import AgentSession, RunContext, function_tool
from livekit.agents.llm import FunctionTool
from livekit.agents.voice.speech_handle import SpeechHandle

logger = logging.getLogger("agent.browser_end_call")

# Must match END_CALL_RPC in frontend/hooks/useAgentEndCall.ts.
END_CALL_RPC = "end_call"
_RPC_TIMEOUT_S = 5.0

_DESCRIPTION = """
Ends the voice chat: the customer's mic turns off once your goodbye has played, and the text
chat stays open. Say your goodbye first, then call this in the same reply.
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
    """Per session: it remembers that a goodbye is under way, so a second end_call
    (the model calling it again from the goodbye it was asked for) does nothing.
    Once the browser has been asked, a later voice chat can be ended again."""

    def __init__(self, *, goodbye_instructions: str, extra_description: str = ""):
        self._goodbye_instructions = goodbye_instructions
        self._ending = False
        self.tool: FunctionTool = function_tool(
            self._end_call,
            name="end_call",
            description=f"{_DESCRIPTION}\n{extra_description}",
        )

    async def _end_call(self, ctx: RunContext) -> str | None:
        if self._ending:
            return None
        # A goodbye interrupted by the customer cancels this tool, and the voice chat goes on.
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
            logger.info("asked the browser to turn the mic off")
        except Exception:
            logger.warning("couldn't ask the browser to turn the mic off", exc_info=True)
        finally:
            self._ending = False
