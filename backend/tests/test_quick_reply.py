"""Quick replies: routing, the filler line and the small model's answer stream.
Requests go to an httpx.MockTransport or a fake LLM, never the network."""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import pytest
from word_checks import real_estate_words
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
    pending_action: object | None = None
    pending_case: object | None = None


# --- route -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("judgement", "expected"),
    [
        (Judgement(0.9, "none", 0.9), "fast"),
        (Judgement(0.9, "none", 0.5), None),  # not sure enough no lookup is needed
        (Judgement(0.9, "packages", 0.8), "filler"),
        (Judgement(0.9, "knowledge_base", 0.8), "filler"),
        (Judgement(0.9, "packages", 0.4), None),  # weak guess at a lookup: no filler line
        (Judgement(0.9, None, None), None),  # the lookup question wasn't asked
        (Judgement(None), None),
        (None, None),
    ],
)
def test_route(judgement, expected):
    assert route(judgement, _Userdata(), _config(), _settings()) == expected


def test_route_off_switches():
    s = _settings()
    none, search = Judgement(0.9, "none", 0.9), Judgement(0.9, "packages", 0.9)
    assert route(none, _Userdata(), _config(quick_reply_enabled=False), s) is None
    assert route(search, _Userdata(), _config(quick_reply_enabled=False), s) is None
    assert route(none, _Userdata(), _config(quick_fast_answer=False), s) is None
    assert route(search, _Userdata(), _config(quick_filler=False), s) is None


@pytest.mark.parametrize("pending", ["pending_action", "pending_case"])
def test_route_is_none_while_something_is_pending(pending):
    userdata = _Userdata(**{pending: object()})
    s = _settings()
    assert route(Judgement(0.9, "none", 0.99), userdata, _config(), s) is None
    assert route(Judgement(0.9, "packages", 0.99), userdata, _config(), s) is None
    assert route(None, userdata, _config(), s, closing=True) is None


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
    assert runtime.avoid("any packs?") == [
        "One moment.", "Looking now.", "Finding those.", "Okay.", "Sure, checking.",
    ]
    assert runtime.avoid("প্যাক আছে?") == ["দেখছি।"]


# --- filler ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "utterance", "ok"),
    [
        ("Let me check the data packs for you.", "any data packs?", True),
        ("আপনার জন্য প্যাকগুলো দেখছি।", "ডাটা প্যাক আছে?", True),
        ("Checking 300 taka packs for you.", "packs under 300 taka?", True),  # echoes their number
        ("We have 4 packs ready for you.", "any packs?", False),  # a number of its own
        ("Balance is 50 taka, one moment.", "what is my balance", False),  # money
        ("Call 01711223344 for the details.", "details?", False),  # contact
        ("Do you want data or minutes?", "packs?", False),  # a question
        ("One two three four five six seven eight nine ten eleven twelve thirteen", "x", False),  # too long
        ("", "x", False),
    ],
)
def test_safe_filler(line, utterance, ok):
    assert (safe_filler(line, utterance) is not None) is ok


def _completion(content: str) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": content}}], "usage": {"cost": 0.00001}}
    )


def _compose(handler, utterance="ডাটা প্যাক আছে?", timeout_s=1.0):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await compose_filler(
                client, _BASE, "or-key", "google/gemini-3.5-flash-lite", utterance, "packages",
                [Exchange("assistant", "কী ধরনের প্যাক চান?")], ["দেখছি।"], timeout_s=timeout_s,
            )  # fmt: skip

    return asyncio.run(go())


def test_compose_filler_request_and_line():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _completion(json.dumps({"text": "আপনার জন্য প্যাকগুলো দেখছি।"}))

    assert _compose(handler) == "আপনার জন্য প্যাকগুলো দেখছি।"
    assert seen["url"] == f"{_BASE}/chat/completions"
    assert seen["auth"] == "Bearer or-key"
    body = seen["body"]
    assert body["model"] == "google/gemini-3.5-flash-lite"
    assert body["reasoning"] == {"effort": "minimal"}
    assert body["provider"]["data_collection"] == "deny"
    assert body["temperature"] == 0
    user = body["messages"][1]["content"]
    assert "Assistant: কী ধরনের প্যাক চান?" in user
    assert "What is being looked up: packages." in user
    assert "Already said (don't repeat): দেখছি।" in user
    assert user.endswith("Customer's new message: ডাটা প্যাক আছে?")


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
    assert quick_reply.FILLER_MAX_WORDS == 12


def test_fast_and_filler_prompts_are_telco_only():
    assert not real_estate_words(FAST_RULES)
    assert not real_estate_words(quick_reply._FILLER_SYSTEM)


def test_fast_rules_hand_off_telco_facts_and_codes():
    for needle in ("balance", "recharge", "4 to 8 digit", "complain", "redeem"):
        assert needle in FAST_RULES


def test_filler_examples_are_telco():
    for line in ("ব্যালেন্সটা চেক করছি।", "প্যাকগুলো দেখছি।", "Checking your account."):
        assert line in quick_reply._FILLER_SYSTEM


# --- template fillers -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("আমার ব্যালেন্স কত আছে?", "filler"),  # an account tool, though Jev says no lookup
        ("আমার টাকা কেটে নিল কেন?", "filler"),
        ("amar balance koto?", "filler"),
        ("ধন্যবাদ, আসসালামু আলাইকুম", "fast"),
        ("ঠিক আছে", "fast"),
    ],
)
def test_route_gives_a_tool_turn_a_filler_whatever_the_lookup(text, expected):
    judgement = Judgement(0.9, "none", 0.9, text=text)
    assert route(judgement, _Userdata(), _config(), _settings()) == expected
    # The turn's own text wins over the judgement's.
    assert route(Judgement(0.9, "none", 0.9), _Userdata(), _config(), _settings(), text=text) == expected


def test_route_never_fills_over_a_pending_action():
    judgement = Judgement(0.9, "none", 0.9, text="রিচার্জ করে দিন")
    assert route(judgement, _Userdata(pending_action=object()), _config(), _settings()) is None


@pytest.mark.parametrize(
    ("utterance", "lookup", "expected"),
    [
        ("আমার ব্যালেন্স কত আছে?", "none", "ব্যালেন্সটা চেক করছি।"),
        ("৩০০ টাকার মধ্যে ১০ জিবি ইন্টারনেট প্যাক কী আছে?", "packages", "ডাটা প্যাকগুলো দেখছি।"),
        ("সাত দিনের মিনিট প্যাক আছে?", "packages", "মিনিট প্যাকগুলো দেখছি।"),
        ("আমার নেটওয়ার্ক কাজ করছে না", "none", "আপনার এলাকার নেটওয়ার্কটা চেক করছি।"),
        ("রোমিং চালু করতে কী লাগে?", "knowledge_base", "ওকে, এক সেকেন্ড।"),
        ("How much data do I have left?", "none", "Checking your usage."),
        ("Show me weekly voice packs under 100 taka.", "packages", "Checking the minute packs."),
        ("amar balance koto ache?", "none", "ব্যালেন্সটা চেক করছি।"),
    ],
)
def test_fast_filler_names_what_was_asked(utterance, lookup, expected):
    assert quick_reply.fast_filler(utterance, lookup) == expected


def test_fast_filler_varies_its_lines_and_openers():
    said: list[str] = []
    for _ in range(4):
        line = quick_reply.fast_filler("আমার ব্যালেন্স কত আছে?", "none", avoid=said)
        assert line not in said
        said.append(line)
    # A topic line first, then the next topic line, then generic ones.
    assert said[:2] == ["ব্যালেন্সটা চেক করছি।", "জি, আপনার ব্যালেন্সটা দেখছি।"]


def test_fast_filler_prefers_a_line_already_cached(tmp_path):
    from app.agent.audio_cache import AudioCache

    cache = AudioCache(tmp_path)
    cache.save("জি, আপনার ব্যালেন্সটা দেখছি।", b"\x00\x00" * 100, 24000, 1, "voice:model")
    assert quick_reply.fast_filler("আমার ব্যালেন্স কত আছে?", "none", cache=cache) == (
        "জি, আপনার ব্যালেন্সটা দেখছি।"
    )


def test_template_lines_are_safe_short_and_telco():
    lines = [
        *quick_reply._GENERIC_BN,
        *quick_reply._GENERIC_EN,
        *(line for lines in quick_reply._TOPIC_LINES_BN.values() for line in lines),
        *(line for lines in quick_reply._TOPIC_LINES_EN.values() for line in lines),
    ]
    for line in lines:
        assert safe_filler(line, "") == line, line
        assert not real_estate_words(line), line
        # The filler prompt's own rule: no literary Bangla.
        assert not any(word in line for word in ("যাচাই", "মিলিয়ে", "ঘেঁটে", "খুলছি")), line
        assert quick_reply.is_filler_line(line)


def test_only_filler_lines_are_cacheable():
    assert quick_reply.is_filler_line("ব্যালেন্সটা চেক করছি")  # punctuation aside
    assert not quick_reply.is_filler_line("আপনার ব্যালেন্স ৫০ টাকা।")
    quick_reply.remember_filler("ওকে, আপনার প্যাকটা দেখছি।")
    assert quick_reply.is_filler_line("ওকে, আপনার প্যাকটা দেখছি।")
