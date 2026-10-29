"""Quick replies in the turn gate: the filler line said while a lookup runs, a
barge-in during it, and the fast route. The small model is faked; the gate's
fakes come from test_gated_session."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from livekit.agents import StopResponse, llm
from livekit.agents.types import FlushSentinel

from app.agent.gated_agent import GateConfig, TurnGateController, _Handled
from app.agent.prefetch import Lookup
from app.agent.quick_reply import QuickReplyRuntime
from app.agent.turn_gate import Thresholds
from app.agent.turn_judge import Judgement
from app.config import Settings
from app.services.agent_config_service import resolve
from test_gated_session import FakeRoom, FakeSession, _heard

_TEXT = "গুলশানে তিন বেডরুমের ফ্ল্যাট আছে?"
_LINE = "আপনার জন্য গুলশানের ফ্ল্যাটগুলো দেখছি।"


class _Handle:
    def __init__(self):
        self.finished = False
        self.interrupted = False

    def done(self):
        return self.finished


class QuickSession(FakeSession):
    def __init__(self):
        super().__init__()
        self.userdata = SimpleNamespace(greeting_done=True)
        self.current_agent = SimpleNamespace(_chat_ctx=SimpleNamespace(items=[]))
        self.handles: list[_Handle] = []
        self.say_error: Exception | None = None

    def say(self, text, **kwargs):
        if self.say_error is not None:
            raise self.say_error
        super().say(text, **kwargs)
        handle = _Handle()
        self.handles.append(handle)
        return handle

    def _conversation_item_added(self, message):
        self.calls.append(("committed", message.text_content))


class FakePrefetcher:
    """Runs a lookup that finishes when `release` is set (at once if None)."""

    def __init__(self, lookups=(), release: asyncio.Event | None = None):
        self.lookups = list(lookups)
        self.release = release
        self.finished = False
        self.cancelled = 0

    def start(self, text, history):
        pass

    def cancel(self):
        self.cancelled += 1

    async def run(self, text, judgement, history, turn_ctx, new_message):
        if self.release is not None:
            await self.release.wait()
        self.finished = True
        return self.lookups


def _gate(
    judgement: Judgement = Judgement(0.9, "listings", 0.9),
    *,
    line: str | None = _LINE,
    compose_s: float = 0.0,
    prefetcher: FakePrefetcher | None = None,
    filler_timeout_ms: int = 2000,
    **config,
):
    session = QuickSession()
    settings = Settings(_env_file=None, filler_timeout_ms=filler_timeout_ms)
    resolved = resolve(None, settings)
    resolved.quick_reply_enabled = True
    for key, value in config.items():
        setattr(resolved, key, value)
    quick = QuickReplyRuntime(resolved, settings, "or-key", httpx.AsyncClient())
    composed: list[str] = []
    topics: list[str | None] = []

    async def compose(text, lookup, history, topic=None):
        composed.append(text)
        topics.append(topic)
        if compose_s:
            await asyncio.sleep(compose_s)
        return line

    quick.compose = compose
    judged: list[tuple[str, str]] = []

    async def judge(text, bot_state, route=False, speaking=""):
        judged.append((text, bot_state))
        return judgement

    fillers: list[tuple[str, float | None, float]] = []
    stored: list[tuple[str, str]] = []
    gate = TurnGateController(
        session=session,
        room=FakeRoom(),
        config=GateConfig(
            thresholds=Thresholds(), interrupt_p=0.5, interrupt_min_words=2, stt_writes_bengali=True
        ),
        judge=judge,
        prefetcher=prefetcher,
        quick=quick,
        on_filler=lambda *args: fillers.append(args),
        on_filler_store=lambda message_id, text: stored.append((message_id, text)),
    )
    gate.attach()
    return SimpleNamespace(
        gate=gate, session=session, composed=composed, judged=judged, fillers=fillers,
        stored=stored, quick=quick, topics=topics,
    )  # fmt: skip


def _msg(text: str = _TEXT) -> llm.ChatMessage:
    return llm.ChatMessage(role="user", content=[text], transcript_confidence=0.9)


async def _turn(g, message: llm.ChatMessage | None = None) -> bool:
    """Hears the final transcript, then completes the turn. False = dropped."""
    message = message or _msg()
    _heard(g.gate, message.text_content)
    try:
        await g.gate.on_user_turn_completed(message, llm.ChatContext())
    except StopResponse:
        return False
    return True


def _says(session) -> list[str]:
    return [call[1] for call in session.calls if call[0] == "say"]


def test_filler_is_said_while_the_lookup_runs():
    async def go():
        release = asyncio.Event()
        prefetcher = FakePrefetcher([], release)
        g = _gate(prefetcher=prefetcher)
        message = _msg()
        turn = asyncio.ensure_future(_turn(g, message))
        for _ in range(50):
            await asyncio.sleep(0.01)
            if _says(g.session):
                break
        assert _says(g.session) == [_LINE]
        assert ("say", _LINE, False) in g.session.calls  # kept out of the chat context
        assert not prefetcher.finished and not turn.done()
        release.set()
        assert await turn is True
        assert g.stored == [(message.id, _LINE)]
        assert g.quick.said == [_LINE]
        assert g.fillers and g.fillers[0][0] == _LINE

    asyncio.run(go())


def test_a_lookup_already_in_the_turn_doesnt_wait_for_the_filler():
    async def go():
        lookup = Lookup("search_apartments", {}, "Found 3", 0.01)
        g = _gate(prefetcher=FakePrefetcher([lookup]), compose_s=1.0)
        message = _msg()
        started = asyncio.get_running_loop().time()
        assert await _turn(g, message) is True
        assert asyncio.get_running_loop().time() - started < 0.5
        assert _says(g.session) == []
        # The line goes on being written, for the reply to speak if it is first.
        pending = g.gate.pending_filler
        assert pending is not None and pending.message_id == message.id
        assert not pending.task.done()

    asyncio.run(go())


def test_without_a_prefetcher_the_filler_is_handed_to_the_reply():
    async def go():
        g = _gate(prefetcher=None, compose_s=0.05)
        assert await _turn(g) is True
        assert _says(g.session) == []
        assert g.gate.pending_filler is not None

    asyncio.run(go())


def test_the_filler_is_said_even_with_the_caller_talking():
    async def go():
        release = asyncio.Event()
        g = _gate(prefetcher=FakePrefetcher([], release))
        g.session.user_state = "speaking"
        turn = asyncio.ensure_future(_turn(g))
        await asyncio.sleep(0.05)
        assert _says(g.session) == [_LINE]
        release.set()
        assert await turn is True

    asyncio.run(go())


def test_a_newer_final_doesnt_skip_the_filler():
    async def go():
        release = asyncio.Event()
        g = _gate(prefetcher=FakePrefetcher([], release), compose_s=0.05)
        message = _msg()
        _heard(g.gate, message.text_content)
        turn = asyncio.ensure_future(g.gate.on_user_turn_completed(message, llm.ChatContext()))
        await asyncio.sleep(0.1)
        release.set()
        await turn
        assert _says(g.session) == [_LINE]

    asyncio.run(go())


# ---- the filler in front of the reply (TurnGateController.with_filler) ----


async def _stream(*items):
    """(delay in seconds, item) pairs as a reply stream."""
    for delay, item in items:
        await asyncio.sleep(delay)
        yield item


async def _collect(stream):
    return [chunk async for chunk in stream]


def _tool_call_chunk():
    return llm.ChatChunk(
        id="x",
        delta=llm.ChoiceDelta(
            role="assistant",
            tool_calls=[llm.FunctionToolCall(name="search_apartments", arguments="{}", call_id="c1")],
        ),
    )


def test_a_filler_ready_before_the_reply_is_spoken_first():
    async def go():
        g = _gate(prefetcher=None, compose_s=0.05)
        message = _msg()
        assert await _turn(g, message) is True
        out = await _collect(g.gate.with_filler(_stream((0.3, "answer")), message.id))
        assert out[0] == _LINE and isinstance(out[1], FlushSentinel) and out[2] == "answer"
        assert g.stored == [(message.id, _LINE)]
        assert g.quick.said == [_LINE] and g.fillers and g.fillers[0][0] == _LINE
        assert g.gate.pending_filler is None
        assert g.gate.filler_segment() is True
        assert g.gate.filler_segment() is False  # once per line

    asyncio.run(go())


def test_a_filler_after_the_reply_started_is_dropped():
    async def go():
        g = _gate(prefetcher=None, compose_s=0.3)
        message = _msg()
        assert await _turn(g, message) is True
        pending = g.gate.pending_filler
        out = await _collect(g.gate.with_filler(_stream((0.05, "answer"), (0, " more")), message.id))
        assert out == ["answer", " more"]
        assert g.stored == [] and g.quick.said == [] and g.fillers == []
        assert g.gate.pending_filler is None and g.gate.filler_segment() is False
        await asyncio.sleep(0)
        assert pending.task.cancelled()

    asyncio.run(go())


def test_a_tool_call_is_not_the_reply_so_the_filler_still_goes_first():
    async def go():
        g = _gate(prefetcher=None, compose_s=0.1)
        message = _msg()
        assert await _turn(g, message) is True
        call = _tool_call_chunk()
        out = await _collect(g.gate.with_filler(_stream((0, call), (0.4, "answer")), message.id))
        assert out[0] is call and out[1] == _LINE and out[3] == "answer"

    asyncio.run(go())


def test_no_filler_line_leaves_the_reply_alone():
    async def go():
        g = _gate(prefetcher=None, line=None, compose_s=0.05)
        message = _msg()
        assert await _turn(g, message) is True
        out = await _collect(g.gate.with_filler(_stream((0.2, "answer")), message.id))
        assert out == ["answer"] and g.stored == []

    asyncio.run(go())


def test_a_barge_in_drops_the_pending_filler():
    async def go():
        g = _gate(prefetcher=None, compose_s=0.3)
        message = _msg()
        assert await _turn(g, message) is True
        pending = g.gate.pending_filler
        await g.gate._barge_in("পার্কিং সহ", stop=False, p=0.9)
        assert g.gate.pending_filler is None
        stream = _stream((0, "answer"))
        assert g.gate.with_filler(stream, message.id) is stream  # nothing to add
        await asyncio.sleep(0)
        assert pending.task.cancelled()

    asyncio.run(go())


def test_a_barge_in_answer_gets_a_filler_on_its_judgement():
    async def go():
        g = _gate(prefetcher=None, compose_s=0.05)
        text = "মিরপুরে ফ্ল্যাট দেখান"
        await g.gate._barge_in(text, stop=False, p=0.9, judgement=Judgement(0.9, "listings", 0.9))
        assert ("generate_reply", text) in g.session.calls
        await asyncio.sleep(0)  # the line's task starts
        assert g.composed == [text]
        assert g.gate.pending_filler is not None
        # The reply's user message only exists once the library adds it: the
        # filler is found by its words, and stored under that message.
        reply = _msg(text)
        out = await _collect(g.gate.with_filler(_stream((0.3, "answer")), reply.id, text))
        assert out[0] == _LINE
        assert g.stored == [(reply.id, _LINE)]

    asyncio.run(go())


def test_a_barge_in_answer_goes_to_the_small_model_on_its_judgement():
    async def go():
        g = _gate(prefetcher=None)
        text = "আপনার নামটা আরেকবার বলবেন?"
        await g.gate._barge_in(text, stop=False, p=0.9, judgement=Judgement(0.9, "none", 0.95))
        assert g.gate.is_fast_reply("any-id", text)
        assert not g.gate.is_fast_reply("any-id", "অন্য কথা")
        assert g.composed == []

    asyncio.run(go())


def test_a_barge_in_without_a_judgement_gets_no_quick_reply():
    async def go():
        g = _gate(prefetcher=None)
        await g.gate._barge_in("থামুন", stop=True, p=None)
        assert g.composed == [] and g.gate.pending_filler is None and g.gate.fast_for is None

    asyncio.run(go())


def test_an_approved_barge_in_turn_gets_the_filler_without_a_second_jev_call():
    async def go():
        g = _gate(prefetcher=None, compose_s=0.05)
        text = "মিরপুরে ফ্ল্যাট দেখান"
        g.gate._approved = _Handled(text, g.gate.clock(), Judgement(0.9, "listings", 0.9))
        message = _msg(text)
        _heard(g.gate, text)
        await g.gate.on_user_turn_completed(message, llm.ChatContext())
        assert g.judged == []  # Jev's answer for the barge-in was reused
        await asyncio.sleep(0)  # the line's task starts
        assert g.composed == [text]
        assert g.gate.pending_filler is not None

    asyncio.run(go())


def test_a_filler_belongs_to_its_own_turn():
    async def go():
        g = _gate(prefetcher=None, compose_s=0.05)
        assert await _turn(g) is True
        stream = _stream((0, "answer"))
        assert g.gate.with_filler(stream, "another-message") is stream
        assert g.gate.pending_filler is not None

    asyncio.run(go())


@pytest.mark.parametrize(
    "config", [{"quick_reply_enabled": False}, {"quick_filler": False}]
)
def test_no_filler_when_switched_off(config):
    async def go():
        g = _gate(prefetcher=None, **config)
        assert await _turn(g) is True
        assert _says(g.session) == []
        assert g.composed == []

    asyncio.run(go())


def test_a_weak_lookup_guess_gets_no_filler():
    async def go():
        g = _gate(Judgement(0.9, "listings", 0.3), prefetcher=None)
        assert await _turn(g) is True
        assert g.composed == [] and _says(g.session) == []

    asyncio.run(go())


def test_the_filler_gets_jevs_topic_only_when_jev_is_sure():
    async def go():
        sure = _gate(Judgement(0.9, "listings", 0.9, topic="balance", topic_p=0.9), prefetcher=None)
        assert await _turn(sure) is True
        unsure = _gate(Judgement(0.9, "listings", 0.9, topic="balance", topic_p=0.4), prefetcher=None)
        assert await _turn(unsure) is True
        await asyncio.sleep(0)  # the lines' tasks start
        assert sure.topics == ["balance"] and unsure.topics == [None]

    asyncio.run(go())


def test_a_failing_say_keeps_the_turn():
    async def go():
        g = _gate(prefetcher=None)
        g.session.say_error = RuntimeError("scheduling paused")
        assert await _turn(g) is True

    asyncio.run(go())


def test_a_cancelled_judge_is_ignored():
    async def go():
        g = _gate()
        task = asyncio.ensure_future(asyncio.sleep(1))
        task.cancel()
        await asyncio.sleep(0)
        g.gate._on_judged(_TEXT, task)
        assert g.composed == []

    asyncio.run(go())


def test_barge_in_during_the_filler_keeps_the_question_and_drops_the_reply():
    async def go():
        release = asyncio.Event()
        prefetcher = FakePrefetcher([], release)
        g = _gate(prefetcher=prefetcher)
        turn = asyncio.ensure_future(_turn(g))
        await asyncio.sleep(0.05)
        assert _says(g.session) == [_LINE]
        # The caller talks over the filler: the gate answers that instead.
        await g.gate._barge_in("পার্কিং সহ", stop=False, p=0.9)
        assert await turn is False
        kinds = [call[0] for call in g.session.calls]
        assert kinds.index("committed") < kinds.index("generate_reply")
        assert ("committed", _TEXT) in g.session.calls
        assert ("generate_reply", "পার্কিং সহ") in g.session.calls

    asyncio.run(go())


def test_a_queued_answer_waits_for_the_turn_and_keeps_its_reply():
    async def go():
        release = asyncio.Event()
        g = _gate(prefetcher=FakePrefetcher([], release))
        turn = asyncio.ensure_future(_turn(g))
        await asyncio.sleep(0.05)
        queued = asyncio.ensure_future(g.gate._answer_after_current("জি", 0.6))
        await asyncio.sleep(0.05)
        assert not queued.done()  # waits for the turn's own reply to be scheduled
        release.set()
        assert await turn is True
        await queued
        assert ("generate_reply", "জি") in g.session.calls
        assert not any(call[0] == "committed" for call in g.session.calls)

    asyncio.run(go())


def test_speech_during_the_filler_is_speech_over_the_agent():
    async def go():
        release = asyncio.Event()
        g = _gate(prefetcher=FakePrefetcher([], release))
        turn = asyncio.ensure_future(_turn(g))
        await asyncio.sleep(0.05)
        release.set()
        assert await turn is True
        assert _says(g.session) == [_LINE]
        g.judged.clear()
        # The library may already say "listening" before the reply's audio.
        g.session.agent_state = "listening"
        _heard(g.gate, "আচ্ছা শুনুন একটা কথা")
        while g.gate._tasks:
            await asyncio.gather(*list(g.gate._tasks))
        assert g.judged == [("আচ্ছা শুনুন একটা কথা", "speaking")]
        g.session.handles[0].finished = True
        g.judged.clear()
        _heard(g.gate, "আরেকটা প্রশ্ন")
        await asyncio.sleep(0)
        assert g.judged == [("আরেকটা প্রশ্ন", "listening")]

    asyncio.run(go())


def test_fast_route_marks_the_message():
    async def go():
        g = _gate(Judgement(0.9, "none", 0.95), prefetcher=None)
        message = _msg("আপনার নামটা আরেকবার বলবেন?")
        assert await _turn(g, message) is True
        assert g.gate.fast_for == message.id
        assert _says(g.session) == []

    asyncio.run(go())


@pytest.mark.parametrize("text", ["ঠিক আছে, ধন্যবাদ", "আচ্ছা, আসি তাহলে", "ok bye bye"])
def test_a_goodbye_goes_to_the_small_model_without_jev(text):
    async def go():
        g = _gate(Judgement(0.1, "listings", 0.9), prefetcher=None)
        message = _msg(text)
        assert await _turn(g, message) is True
        assert g.gate.fast_for == message.id
        assert _says(g.session) == []

    asyncio.run(go())


# ---- the small model answers (GatedAgent.llm_node) ----


class _FakeLLM:
    def __init__(self, texts):
        self.texts = texts
        self.calls: list[dict] = []
        self.handlers: dict = {}

    def on(self, event, callback):
        self.handlers[event] = callback

    def chat(self, *, chat_ctx, tools, conn_options):
        self.calls.append({"ctx": chat_ctx, "tools": tools})
        texts = self.texts

        class _Stream:
            async def __aenter__(self_inner):
                async def gen():
                    for text in texts:
                        yield llm.ChatChunk(id="x", delta=llm.ChoiceDelta(role="assistant", content=text))

                return gen()

            async def __aexit__(self_inner, *exc):
                return False

        return _Stream()


def _agent(monkeypatch, fast_texts):
    from livekit.agents import Agent

    from app.agent.gated_agent import GatedAgent

    g = _gate(Judgement(0.9, "none", 0.95), prefetcher=None)
    fast = _FakeLLM(fast_texts)
    g.quick._fast_llm = fast
    main_calls: list = []

    async def main_node(agent, chat_ctx, tools, model_settings):
        main_calls.append(chat_ctx)
        yield "main answer"

    monkeypatch.setattr(Agent.default, "llm_node", staticmethod(main_node))
    routed: list[bool] = []
    g.gate.on_fast = routed.append
    agent = GatedAgent(gate=g.gate, instructions="You are Nadia.")
    return agent, g, fast, main_calls, routed


@llm.function_tool
async def end_call() -> None:
    """End the call."""


@llm.function_tool
async def search_apartments() -> None:
    """Search."""


def _reply(agent, ctx, tools):
    async def go():
        out = []
        async for chunk in agent.llm_node(ctx, tools, None):
            out.append(chunk if isinstance(chunk, str) else chunk.delta.content)
        return "".join(out)

    return asyncio.run(go())


def _ctx_with(message: llm.ChatMessage) -> llm.ChatContext:
    from livekit.agents.voice.generation import INSTRUCTIONS_MESSAGE_ID

    ctx = llm.ChatContext()
    ctx.items.append(
        llm.ChatMessage(id=INSTRUCTIONS_MESSAGE_ID, role="system", content=["You are Nadia."])
    )
    ctx.items.append(llm.FunctionCall(call_id="c1", name="search_apartments", arguments="{}"))
    ctx.items.append(
        llm.FunctionCallOutput(call_id="c1", name="search_apartments", output="[]", is_error=False)
    )
    ctx.items.append(message)
    return ctx


def test_the_small_model_answers_its_own_turn(monkeypatch):
    agent, g, fast, main_calls, routed = _agent(monkeypatch, ["আমি নাদিয়া, ", "বলুন কীভাবে সাহায্য করতে পারি।"])
    message = _msg("আপনার নামটা আরেকবার বলবেন?")
    g.gate.fast_for = message.id
    ctx, tools = _ctx_with(message), [search_apartments, end_call]
    assert _reply(agent, ctx, tools) == "আমি নাদিয়া, বলুন কীভাবে সাহায্য করতে পারি।"
    assert main_calls == [] and routed == [False]
    assert g.gate.fast_for is None
    # Only end_call, in a new list; the turn's own list and context are untouched.
    assert fast.calls[0]["tools"] == [end_call]
    assert tools == [search_apartments, end_call]
    assert [item.type for item in fast.calls[0]["ctx"].items] == ["message", "message"]
    assert len(ctx.items) == 4


def test_a_handoff_goes_to_the_main_model(monkeypatch):
    agent, g, fast, main_calls, routed = _agent(monkeypatch, ["[[MAIN]]"])
    message = _msg()
    g.gate.fast_for = message.id
    assert _reply(agent, _ctx_with(message), [end_call]) == "main answer"
    assert len(main_calls) == 1 and routed == [True]


def test_the_small_model_gets_the_real_end_call_tool(monkeypatch):
    """EndCallTool is a toolset; the reply's tools come flattened, and only its
    end_call function reaches the small model."""
    from livekit.agents.beta.tools.end_call import EndCallTool

    agent, g, fast, main_calls, routed = _agent(monkeypatch, ["Thanks for calling, goodbye!"])
    message = _msg("ok bye bye")
    g.gate.fast_for = message.id
    tools = llm.ToolContext([search_apartments, EndCallTool(delete_room=True)]).flatten()
    assert _reply(agent, _ctx_with(message), tools) == "Thanks for calling, goodbye!"
    assert [tool.id for tool in fast.calls[0]["tools"]] == ["end_call"]
    assert len(tools) == 2


def test_a_later_reply_uses_the_main_model(monkeypatch):
    """The routed turn's reply never ran (dropped); a barge-in reply for another
    message must not go to the small model."""
    agent, g, fast, main_calls, routed = _agent(monkeypatch, ["hello"])
    g.gate.fast_for = _msg("old turn").id
    assert _reply(agent, _ctx_with(_msg("a new question")), [end_call]) == "main answer"
    assert fast.calls == [] and routed == []


# ---- GatedAgent: the filler segment and llm_node ----


def test_the_filler_segment_stays_out_of_the_transcript():
    from app.agent.gated_agent import GatedAgent

    g = _gate(prefetcher=None)
    agent = GatedAgent(gate=g.gate, instructions="You are Nadia.")

    async def text(*parts):
        for part in parts:
            yield part

    async def forwarded(source):
        return [delta async for delta in agent.transcription_node(source, None)]

    async def go():
        g.gate._filler_segment = True
        assert await forwarded(text(_LINE)) == []
        assert _LINE in list(g.gate._bot_texts)  # still known to the echo check
        assert await forwarded(text("answer")) == ["answer"]

    asyncio.run(go())


def test_llm_node_puts_the_filler_before_the_main_reply(monkeypatch):
    from livekit.agents import Agent

    from app.agent.gated_agent import GatedAgent

    g = _gate(prefetcher=None, compose_s=0.05)

    async def main_node(agent, chat_ctx, tools, model_settings):
        await asyncio.sleep(0.3)
        yield "main answer"

    monkeypatch.setattr(Agent.default, "llm_node", staticmethod(main_node))
    agent = GatedAgent(gate=g.gate, instructions="You are Nadia.")
    message = _msg()

    async def go():
        assert await _turn(g, message) is True
        out = []
        async for chunk in agent.llm_node(_ctx_with(message), [], None):
            out.append(chunk)
        return out

    out = asyncio.run(go())
    assert out[0] == _LINE and isinstance(out[1], FlushSentinel) and out[2] == "main answer"
