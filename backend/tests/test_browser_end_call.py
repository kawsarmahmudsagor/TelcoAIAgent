import asyncio
from types import SimpleNamespace

from livekit.agents import llm

from app.agent import browser_end_call
from app.agent.browser_end_call import END_CALL_RPC, BrowserEndCall

GOODBYE = "say goodbye"


class _Handle:
    def __init__(self, items):
        self.chat_items = items
        self.interrupted = False
        self.callbacks = []

    def add_done_callback(self, cb):
        self.callbacks.append(cb)

    def finish(self, interrupted=False):
        self.interrupted = interrupted
        for cb in self.callbacks:
            cb(self)


class _Session:
    def __init__(self, caller="browser-user"):
        self.rpcs = []
        self.on_close = []

        async def perform_rpc(**kwargs):
            self.rpcs.append(kwargs)
            return ""

        participant = SimpleNamespace(identity=caller) if caller else None
        self.room_io = SimpleNamespace(
            linked_participant=participant,
            room=SimpleNamespace(local_participant=SimpleNamespace(perform_rpc=perform_rpc)),
        )

    def once(self, event, cb):
        assert event == "close"
        self.on_close.append(cb)

    def close(self):
        for cb in self.on_close:
            cb(None)


def _ctx(session, text, *, generation="gen_1", interrupted=False):
    items = [llm.FunctionCall(id=f"{generation}/fnc_0", call_id="c1", name="end_call", arguments="{}")]
    if text is not None:
        items.insert(
            0,
            llm.ChatMessage(
                role="assistant", content=[text], id=generation, interrupted=interrupted
            ),
        )

    async def wait_for_playout():
        return None

    return SimpleNamespace(
        session=session,
        speech_handle=_Handle(items),
        function_call=items[-1],
        wait_for_playout=wait_for_playout,
    )


def test_goodbye_before_it_asks_the_browser_and_wants_no_reply():
    async def go():
        tool, session = BrowserEndCall(goodbye_instructions=GOODBYE), _Session()
        out = await tool._end_call(_ctx(session, "ধন্যবাদ, আবার কথা হবে।"))
        assert out is None
        assert session.rpcs == [
            {
                "destination_identity": "browser-user",
                "method": END_CALL_RPC,
                "payload": "",
                "response_timeout": 5.0,
            }
        ]
        session.close()  # the browser ended the call: no fallback

    asyncio.run(go())


def test_no_goodbye_asks_for_one_and_ends_after_it_played():
    async def go():
        tool, session = BrowserEndCall(goodbye_instructions=GOODBYE), _Session()
        ctx = _ctx(session, None)
        assert await tool._end_call(ctx) == GOODBYE
        assert session.rpcs == []
        # The model calls end_call again from the goodbye it was asked for.
        assert await tool._end_call(_ctx(session, "Bye!", generation="gen_2")) is None
        assert session.rpcs == []
        ctx.speech_handle.finish()
        await asyncio.sleep(0)
        assert len(session.rpcs) == 1
        session.close()

    asyncio.run(go())


def test_goodbye_from_an_earlier_step_does_not_count():
    async def go():
        tool, session = BrowserEndCall(goodbye_instructions=GOODBYE), _Session()
        ctx = _ctx(session, None, generation="gen_2")
        ctx.speech_handle.chat_items.insert(
            0, llm.ChatMessage(role="assistant", content=["Let me check."], id="gen_1")
        )
        assert await tool._end_call(ctx) == GOODBYE

    asyncio.run(go())


def test_an_interrupted_goodbye_reply_keeps_the_call_going():
    async def go():
        tool, session = BrowserEndCall(goodbye_instructions=GOODBYE), _Session()
        ctx = _ctx(session, None)
        await tool._end_call(ctx)
        ctx.speech_handle.finish(interrupted=True)
        await asyncio.sleep(0)
        assert session.rpcs == []
        # The customer went on; a later goodbye ends the call.
        assert await tool._end_call(_ctx(session, "Bye!", generation="gen_3")) is None
        assert len(session.rpcs) == 1
        session.close()

    asyncio.run(go())


def test_room_is_deleted_when_the_browser_never_ends_the_call(monkeypatch):
    calls = []

    async def delete_room():
        calls.append("delete_room")

    job = SimpleNamespace(delete_room=delete_room, shutdown=lambda reason: calls.append(reason))
    monkeypatch.setattr(browser_end_call, "get_job_context", lambda: job)

    async def go():
        tool = BrowserEndCall(goodbye_instructions=GOODBYE, fallback_s=0.01)
        session = _Session(caller=None)  # no browser to ask
        assert await tool._end_call(_ctx(session, "Bye!")) is None
        await asyncio.sleep(0.05)

    asyncio.run(go())
    assert calls == ["delete_room", "browser did not end the call"]
