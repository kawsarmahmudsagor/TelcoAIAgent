"""Quick replies: routing, the filler line and the small model's answer stream.
Requests go to an httpx.MockTransport or a fake LLM, never the network."""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import pytest
from livekit.agents import llm
from livekit.agents.voice.generation import INSTRUCTIONS_MESSAGE_ID

from app.agent import quick_reply
from app.agent.quick_reply import (
    FAST_RULES,
    HANDOFF,
    Handoff,
    QuickReplyRuntime,
    compose_filler,
    end_call_tools,
    fast_chat_ctx,
    route,
    safe_filler,
    stream_fast,
)
from app.agent.turn_judge import Exchange, Judgement
from app.config import Settings
from app.services.agent_config_service import resolve

_BASE = "https://openrouter.ai/api/v1"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _config(**overrides):
    config = resolve(None, _settings())
    config.quick_reply_enabled = True
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


@dataclass
class _Userdata:
    pass


# --- route -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("judgement", "expected"),
    [
        (Judgement(0.9, "none", 0.9), "fast"),
        (Judgement(0.9, "none", 0.5), None),  # not sure enough no lookup is needed
        (Judgement(0.9, "listings", 0.8), "filler"),
        (Judgement(0.9, "knowledge_base", 0.8), "filler"),
        (Judgement(0.9, "offers", 0.4), None),  # weak guess at a search: no "let me find that"
        (Judgement(0.9, None, None), None),  # the lookup question wasn't asked
        (Judgement(None), None),
        (None, None),
    ],
)
def test_route(judgement, expected):
    assert route(judgement, _Userdata(), _config(), _settings()) == expected


def test_route_off_switches():
    s = _settings()
    none, search = Judgement(0.9, "none", 0.9), Judgement(0.9, "listings", 0.9)
    assert route(none, _Userdata(), _config(quick_reply_enabled=False), s) is None
    assert route(search, _Userdata(), _config(quick_reply_enabled=False), s) is None
    assert route(none, _Userdata(), _config(quick_fast_answer=False), s) is None
    assert route(search, _Userdata(), _config(quick_filler=False), s) is None


def test_a_goodbye_goes_to_the_small_model_without_jev():
    s = _settings()
    assert route(None, _Userdata(), _config(), s, closing=True) == "fast"
    assert route(None, _Userdata(), _config(quick_fast_answer=False), s, closing=True) is None
    assert route(None, _Userdata(), _config(quick_reply_enabled=False), s, closing=True) is None


def test_avoid_keeps_the_utterance_script():
    runtime = QuickReplyRuntime(_config(), _settings(), "k", httpx.AsyncClient())
    runtime.said = [
        "Let me check.", "দেখছি।", "One moment.", "Looking now.", "Finding those.",
        "Okay.", "Sure, checking.",
    ]
    assert runtime.avoid("any flats?") == [
        "One moment.", "Looking now.", "Finding those.", "Okay.", "Sure, checking.",
    ]
    assert runtime.avoid("ফ্ল্যাট আছে?") == ["দেখছি।"]


# --- filler ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "utterance", "ok"),
    [
        ("Let me find those Gulshan flats for you.", "flats in Gulshan?", True),
        ("আপনার জন্য গুলশানের ফ্ল্যাটগুলো দেখছি।", "গুলশানে ফ্ল্যাট আছে?", True),
        ("Finding 3 bedroom flats for you.", "3 bedroom flats?", True),  # echoes their number
        ("We have 4 flats ready for you.", "any flats?", False),  # a number of its own
        ("Flats from 50 lakh, one moment.", "flats with 50 parking", False),  # money
        ("Call 01711223344 for the details.", "details?", False),  # contact
        ("Do you want rent or buy?", "flats?", False),  # a question
        ("One two three four five six seven eight nine ten eleven", "x", False),  # too long
        ("", "x", False),
    ],
)
def test_safe_filler(line, utterance, ok):
    assert (safe_filler(line, utterance) is not None) is ok


def _completion(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": content}}], "usage": {"cost": 0.00001}}
    )


def _compose(handler, utterance="গুলশানে ফ্ল্যাট আছে?", timeout_s=1.0):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await compose_filler(
                client, _BASE, "or-key", "google/gemini-3.5-flash-lite", utterance, "listings",
                [Exchange("assistant", "কী ধরনের বাসা খুঁজছেন?")], ["দেখছি।"], timeout_s=timeout_s,
            )  # fmt: skip

    return asyncio.run(go())


def test_compose_filler_request_and_line():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _completion(json.dumps({"text": "আপনার জন্য গুলশানের ফ্ল্যাটগুলো দেখছি।"}))

    assert _compose(handler) == "আপনার জন্য গুলশানের ফ্ল্যাটগুলো দেখছি।"
    assert seen["url"] == f"{_BASE}/chat/completions"
    assert seen["auth"] == "Bearer or-key"
    body = seen["body"]
    assert body["model"] == "google/gemini-3.5-flash-lite"
    assert body["reasoning"] == {"effort": "minimal"}
    assert body["provider"]["data_collection"] == "deny"
    assert body["temperature"] == 0
    user = body["messages"][1]["content"]
    assert "Assistant: কী ধরনের বাসা খুঁজছেন?" in user
    assert "What is being looked up: listings." in user
    assert "Already said (don't repeat): দেখছি।" in user
    assert user.endswith("Customer's new message: গুলশানে ফ্ল্যাট আছে?")


def test_compose_filler_drops_unsafe_and_broken_answers():
    assert _compose(lambda r: _completion(json.dumps({"text": "আমাদের ৪টি ফ্ল্যাট আছে।"}))) is None
    assert _compose(lambda r: _completion("not json")) is None
    assert _compose(lambda r: httpx.Response(500)) is None


def test_compose_filler_times_out():
    async def slow(request):
        await asyncio.sleep(1)
        return _completion(json.dumps({"text": "One moment."}))

    assert _compose(slow, timeout_s=0.05) is None


# --- fast answer -----------------------------------------------------------------------


def _ctx() -> llm.ChatContext:
    ctx = llm.ChatContext()
    ctx.items.append(
        llm.ChatMessage(id=INSTRUCTIONS_MESSAGE_ID, role="system", content=["You are Nadia."])
    )
    ctx.add_message(role="user", content="hello")
    ctx.items.append(llm.FunctionCall(call_id="c1", name="search_apartments", arguments="{}"))
    ctx.items.append(
        llm.FunctionCallOutput(call_id="c1", name="search_apartments", output="[]", is_error=False)
    )
    ctx.add_message(role="assistant", content="Hi! How can I help?")
    return ctx


def test_fast_chat_ctx_adds_rules_without_touching_the_original():
    original = _ctx()
    ctx = fast_chat_ctx(original)
    assert ctx.get_by_id(INSTRUCTIONS_MESSAGE_ID).text_content == "You are Nadia." + FAST_RULES
    assert original.get_by_id(INSTRUCTIONS_MESSAGE_ID).text_content == "You are Nadia."
    assert [item.type for item in ctx.items] == ["message", "message", "message"]
    assert len(original.items) == 5


def test_end_call_tools_is_a_new_list():
    @llm.function_tool
    async def end_call() -> None:
        """End the call."""

    @llm.function_tool
    async def search_apartments() -> None:
        """Search."""

    tools = [search_apartments, end_call]
    picked = end_call_tools(tools)
    assert picked == [end_call]
    assert tools == [search_apartments, end_call]


def _text(content: str) -> llm.ChatChunk:
    return llm.ChatChunk(id="x", delta=llm.ChoiceDelta(role="assistant", content=content))


def _tool_call() -> llm.ChatChunk:
    call = llm.FunctionToolCall(name="end_call", arguments="{}", call_id="t1")
    return llm.ChatChunk(id="x", delta=llm.ChoiceDelta(role="assistant", tool_calls=[call]))


class _FakeLLM:
    def __init__(self, items, delay_s: float = 0.0):
        self.items = items
        self.delay_s = delay_s
        self.tools = None

    @asynccontextmanager
    async def _stream(self):
        async def gen():
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            for item in self.items:
                if isinstance(item, Exception):
                    raise item
                yield item

        yield gen()

    def chat(self, *, chat_ctx, tools, conn_options):
        self.tools = tools
        assert conn_options.max_retry == 0
        return self._stream()


def _run(fake, buffer_chars=24, timeout_s=0.5):
    async def go():
        out = []
        async for item in stream_fast(
            fake, llm.ChatContext(), [], buffer_chars=buffer_chars, first_chunk_timeout_s=timeout_s
        ):
            out.append(item if isinstance(item, str) else "<tool>")
        return out

    return asyncio.run(go())


def test_fast_answer_passes_through():
    out = _run(_FakeLLM([_text("Hello! I'm Nadia, "), _text("how can I help "), _text("you today?")]))
    assert "".join(out) == "Hello! I'm Nadia, how can I help you today?"


def test_short_answer_still_comes_out():
    assert _run(_FakeLLM([_text("জি, বলুন।")])) == ["জি, বলুন।"]


def test_tool_call_flushes_the_buffer():
    assert _run(_FakeLLM([_text("Goodbye!"), _tool_call()])) == ["Goodbye!", "<tool>"]


@pytest.mark.parametrize(
    "items",
    [
        [_text(HANDOFF)],
        [_text("[[MA"), _text("IN]]")],
        [],
        [_text("  ")],
        [RuntimeError("boom")],
        [_text("Sure, "), RuntimeError("boom")],
    ],
)
def test_hands_off_before_speaking(items):
    with pytest.raises(Handoff):
        _run(_FakeLLM(items))


def test_hands_off_when_too_slow_to_start():
    with pytest.raises(Handoff):
        _run(_FakeLLM([_text("Hello there, how can I help?")], delay_s=0.3), timeout_s=0.05)


def test_error_after_speaking_just_ends():
    out = _run(_FakeLLM([_text("Hello! I'm Nadia, how can"), RuntimeError("boom")]))
    assert out == ["Hello! I'm Nadia, how can"]


def test_late_handoff_marker_is_never_spoken():
    out = _run(_FakeLLM([_text("Hello! I'm Nadia, how can"), _text(f" I help?{HANDOFF}")]))
    assert HANDOFF not in "".join(out)


def test_marker_cut_at_the_buffer_edge_is_never_spoken():
    out = _run(_FakeLLM([_text("Let me pass this on now [[MA"), _text("IN]] thanks")]), buffer_chars=24)
    assert "[[" not in "".join(out)
    assert "".join(out) == "Let me pass this on now  thanks"


def test_quick_reply_module_imports_without_a_worker():
    assert quick_reply.FILLER_MAX_WORDS == 10
