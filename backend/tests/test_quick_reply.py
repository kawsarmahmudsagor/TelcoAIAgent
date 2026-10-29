"""Quick replies: routing, the filler line and the small model's answer stream.
Requests go to an httpx.MockTransport or a fake LLM, never the network."""

import asyncio
import json
import random
import re
import unicodedata
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
import pytest
from word_checks import real_estate_words
from livekit.agents import llm
from livekit.agents.voice.generation import INSTRUCTIONS_MESSAGE_ID

from app.agent import quick_reply, reply_punctuation, turn_gate
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
    for line in ("ব্যালেন্সটা চেক করে জানাচ্ছি।", "প্যাকেজগুলো দেখে বলছি।", "Checking your account."):
        assert line in quick_reply._FILLER_SYSTEM


# --- template fillers -------------------------------------------------------------------


def _fillers(utterance, lookup="none", n=200, seed=7, **kwargs):
    rng = random.Random(seed)
    return [quick_reply.fast_filler(utterance, lookup, rng=rng, **kwargs) for _ in range(n)]


@pytest.mark.parametrize(
    ("utterance", "lookup", "echoed"),
    [
        ("আমার ব্যালেন্স কত আছে?", "none", "ব্যালেন্সটা"),
        ("সাত দিনের মিনিট প্যাক আছে?", "packages", "সাত দিনের মিনিট প্যাকেজগুলো"),
        ("৩০০ টাকার মধ্যে ১০ জিবি ইন্টারনেট প্যাক কী আছে?", "packages", "আপনার বাজেটের মধ্যে ১০ জিবির ডাটা প্যাকেজগুলো"),
        ("আমার নেটওয়ার্ক কাজ করছে না", "none", "আপনার এলাকা"),
        ("মিরপুরে নেট পাচ্ছি না", "none", "মিরপুর এলাকার নেটওয়ার্কটা"),
        ("অফিসে নেট পাই না", "none", "আপনার এলাকা"),
        ("আমার ৫০ টাকা কেটে গেছে", "none", "কেটেছে|ট্রানজেকশনগুলো"),
        ("How much data do I have left?", "none", "usage|used"),
        ("Show me weekly voice packs under 100 taka.", "packages", "the weekly minute packages within your budget"),
        ("Where is the care centre near Dhanmondi?", "none", "the care centre nearest Dhanmondi"),
        ("amar balance koto ache?", "none", "ব্যালেন্সটা"),
    ],
)
def test_fast_filler_names_what_was_asked(utterance, lookup, echoed):
    for line in set(_fillers(utterance, lookup, n=50)):
        assert re.search(echoed, line), line


@pytest.mark.parametrize(
    ("utterance", "echoed"),
    [
        # What comes after the last "না" is what they want.
        ("না, ডাটা না, মিনিট চাচ্ছিলাম", "মিনিট প্যাকেজ"),
        ("না, আমার ব্যালেন্সটা দেখেন", "ব্যালেন্সটা"),
        ("No, I want monthly data packs", "the monthly data packages"),
    ],
)
def test_fast_filler_follows_a_correction(utterance, echoed):
    for line in set(_fillers(utterance, "packages", n=50)):
        assert echoed in line, line


@pytest.mark.parametrize(
    ("utterance", "pool"),
    [
        # Nothing asked for instead: no topic is named back.
        ("ডাটা প্যাক চাই না", quick_reply._CORRECTION_BN),
        ("I didn't ask for that", quick_reply._CORRECTION_EN),
        ("দ্বিতীয়টা কিনে দিন", quick_reply._CHOICE_BN),
        ("দুই নম্বরটা কেমন?", quick_reply._CHOICE_BN),
        ("the second one please", quick_reply._CHOICE_EN),
    ],
)
def test_fast_filler_answers_a_correction_or_a_pick_from_its_pool(utterance, pool):
    assert set(_fillers(utterance, n=50)) <= set(pool)


@pytest.mark.parametrize(
    ("utterance", "echoed"),
    [
        # run_26: both got "ডাটা প্যাকেজগুলো ...", a search, for one package.
        ("দুই জিবির প্যাকেজটা দেখান", "দুই জিবির প্যাকেজটা"),
        ("তিন জিবি-র প্যাকেট একটু details বলুন।", "তিন জিবির প্যাকেজটা"),
        # run_27.
        ("হ্যাঁ, আমাকে দুই জিবির অপশনটা দেখান", "দুই জিবির প্যাকেজটা"),
        ("দুই জিবির প্যাকটি সম্পর্কে একটু details বলুন", "দুই জিবির প্যাকেজটা"),
        ("দুই জিবিরটা দেখান", "দুই জিবির প্যাকেজটা"),
        ("সাত দিনের প্যাকেজটার বিস্তারিত বলুন", "সাত দিনের প্যাকেজটা"),
        ("Tell me about the 3 GB package", "the 3 GB package"),
    ],
)
def test_one_package_is_named_not_searched_for(utterance, echoed):
    for line in set(_fillers(utterance, "packages", n=50)):
        assert echoed in line, line
        assert "গুলো" not in line and "packages" not in line, line


def test_one_package_without_a_size_gets_a_line_about_that_one():
    assert set(_fillers("প্যাকেজটার details বলুন", "packages", n=50)) <= set(quick_reply._CHOICE_BN)


def test_asking_which_package_is_still_about_the_list():
    for line in set(_fillers("কোন প্যাকেজটা ভালো হবে?", "packages", n=50)):
        assert "প্যাকেজগুলো" in line, line


@pytest.mark.parametrize(
    ("utterance", "echoed"),
    [
        ("৩০০ টাকার মধ্যে ১০ জিবি ইন্টারনেট প্যাক কী আছে?", "আপনার বাজেটের মধ্যে ১০ জিবির ডাটা প্যাকেজগুলো"),
        # All three would be over the word limit: the budget goes.
        ("সাত দিনের ১০ জিবি প্যাক, ৩০০ টাকার মধ্যে", "সাত দিনের ১০ জিবির ডাটা প্যাকেজগুলো"),
        ("১০০ মিনিটের প্যাক আছে?", "১০০ মিনিটের প্যাকেজগুলো"),
        ("Show me 10 GB data packs", "the 10 GB data packages"),
    ],
)
def test_a_size_is_echoed_as_said(utterance, echoed):
    for line in set(_fillers(utterance, "packages", n=50)):
        assert echoed in line, line
        assert safe_filler(line, unicodedata.normalize("NFC", utterance)) == line


def test_one_package_in_latin_letters():
    # The 3:40 PM call: "pack টি" got "তিন জিবির ডাটা প্যাকেজগুলো".
    for line in set(_fillers("আচ্ছা আমাকে তিন GB-র pack টি সম্পর্কে একটু বলুন", "packages", n=50)):
        assert "তিন জিবির প্যাকেজটা" in line, line


@pytest.mark.parametrize(
    ("last", "utterance", "pool"),
    [
        # The same package again: no need to name it.
        ("জি, দুই জিবির প্যাকেজটা চেক করছি।", "এই প্যাকেজটি সম্পর্কে details বলুন",
         quick_reply._FOLLOW_UP_BN),
        ("জি, ডাটা প্যাকেজগুলো খুঁজছি।", "ডাটা প্যাকগুলোর দাম কত?", quick_reply._FOLLOW_UP_BN),
    ],
)
def test_a_follow_up_gets_a_short_line(last, utterance, pool):
    assert set(_fillers(utterance, "packages", n=50, avoid=[last])) <= set(pool)


def test_something_new_after_something_specific_is_named_with_also():
    lines = set(_fillers("চার জিবির কোনো প্যাকেজ আছে?", "packages", n=50,
                         avoid=["জি, তিন জিবির প্যাকেজটা চেক করছি।"]))
    assert all("চার জিবির ডাটা প্যাকেজগুলোও" in line for line in lines), lines


def test_a_new_topic_is_named_not_followed_up():
    # Data, then minutes: say it is minutes now.
    lines = set(_fillers("মিনিটের কি কি package আছে?", "packages", n=50,
                         avoid=["জি, তিন জিবির প্যাকেজটা চেক করছি।"]))
    assert all("মিনিট" in line for line in lines), lines


@pytest.mark.parametrize(
    "utterance",
    ["হ্যাঁ, আরও কিছু options দেখান", "তিন জিবি কি আর কোনো package available আছে?",
     "এগুলো ছাড়া কি আর কোন options আছে?"],
)
def test_more_gets_more_lines(utterance):
    assert set(_fillers(utterance, "packages", n=50)) <= set(quick_reply._MORE_BN)


@pytest.mark.parametrize(
    "utterance",
    ["হ্যাঁ, এই প্যাকেজটা নিতে চাচ্ছি", "হ্যাঁ তাহলে আগে রিচার্জ করুন",
     "আ, বিকাশে পাঁচশো টাকা রিচার্জ করব", "হ্যাঁ, প্যাকেজটি কিনতে চাই।"],
)
def test_a_purchase_or_recharge_asked_for(utterance):
    assert set(_fillers(utterance, "none", n=50)) <= set(quick_reply._ACTION_BN)


def test_wanting_a_package_and_asking_what_exists_gets_a_neutral_line():
    # The reply asks what kind first, so the filler doesn't promise a search.
    for line in set(_fillers("আমি নতুন একটা প্যাকেজ নিতে চাচ্ছি, কী কী options আছে?", "packages", n=50)):
        assert line not in quick_reply._ACTION_BN and line in quick_reply._GENERIC_BN, line


def test_a_complaint_ending_in_na_is_not_a_correction():
    for line in set(_fillers("আমার নেট পাচ্ছি না", n=50)):
        assert "নেটওয়ার্ক" in line, line


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("মিরপুরে না, উত্তরায় কাস্টমার কেয়ার কোথায়?", ("উত্তরা", "Uttara")),
        ("not in Gulshan, I'm in Banani", ("বনানী", "Banani")),
        ("No network in Old Dhaka", ("পুরান ঢাকা", "Old Dhaka")),
        ("গাজীপুরে নেট নাই", ("গাজীপুর", "Gazipur")),
        # Not a place the care-centre finder knows.
        ("Bogus Town e net nai", None),
    ],
)
def test_place_is_the_last_one_not_negated(utterance, expected):
    assert quick_reply._place(unicodedata.normalize("NFC", utterance)) == expected


def test_places_are_only_the_care_centre_finders():
    from app.bss import care_centres

    known = set(care_centres.DISTRICTS) | set(care_centres.DHAKA_AREAS)
    assert {en for _, _, en in quick_reply._PLACES} == known


@pytest.mark.parametrize(
    ("utterance", "expected"),
    [
        ("Do you have any minute packages?", "voice"),
        ("কোনো মিনিট প্যাকেজ আছে?", "voice"),
        # "slow" alone is not the network.
        ("My recharge is slow to arrive", "recharge"),
        ("My internet is very slow", "network"),
        # "কেটে" is a dropped call before it is a money cut.
        ("লাইন বারবার কেটে যাচ্ছে", "network"),
        ("আমার ৫০ টাকা কেটে গেছে", "transactions"),
        ("amar taka keno kete nilo?", "transactions"),
        # What is left in their pack, not packs to buy.
        ("How much data is left in my data pack?", "usage"),
        ("আমার প্যাকে কতটুকু ডাটা বাকি আছে?", "usage"),
        ("data pack koto taka?", "data"),
        ("ব্যালেন্স কত বাকি?", "balance"),
        # A precomposed য় (U+09DF), as some speech-to-text writes it.
        ("আমার নেটওয়ার্ক নেই", "network"),
        ("আমার কত পয়েন্ট আছে?", "points"),
        ("কাছের কাস্টমার কেয়ার কোথায়?", "care"),
        ("Where is your nearest branch?", "care"),
        # The network before a care centre: an office is where the signal is bad.
        ("অফিসে নেট পাই না", "network"),
    ],
)
def test_filler_topic_tells_close_topics_apart(utterance, expected):
    assert quick_reply._filler_topic(utterance, None) == expected


def test_a_call_does_not_always_open_with_the_same_line():
    picks = Counter(_fillers("আমার ব্যালেন্স কত আছে?"))
    assert len(picks) >= 4
    assert max(picks.values()) <= 100  # none is half the draws


def test_the_customers_own_words_come_before_the_plain_topic():
    own = quick_reply._echo_lines("network", "মিরপুর এলাকার নেটওয়ার্কটা", True)
    assert set(_fillers("মিরপুরে নেট পাচ্ছি না", n=50)) <= set(own)


def test_a_line_that_fits_always_beats_a_generic_one():
    picks = set(_fillers("আমার ব্যালেন্স কত আছে?"))
    assert not picks & set(quick_reply._GENERIC_BN)


@pytest.mark.parametrize(
    "utterance",
    ["আমার ব্যালেন্স কত আছে?", "মিরপুরে নেট পাচ্ছি না", "ডাটা প্যাক আছে?", "How much is my balance?"],
)
def test_fillers_in_a_row_never_share_an_opener_or_a_verb(utterance):
    rng = random.Random(3)
    said: list[str] = []
    for _ in range(6):
        line = quick_reply.fast_filler(utterance, "none", avoid=said[-5:], rng=rng)
        if said:
            assert quick_reply._opener(line) != quick_reply._opener(said[-1]), (said[-1], line)
            assert quick_reply._verb(line) != quick_reply._verb(said[-1]), (said[-1], line)
        said.append(line)
    assert len(set(said)) == len(said)


def test_a_line_already_cached_is_picked_more_often(tmp_path):
    from app.agent.audio_cache import AudioCache

    cached = "আচ্ছা, আপনার ব্যালেন্সটা দেখে জানাচ্ছি।"
    cache = AudioCache(tmp_path)
    cache.save(cached, b"\x00\x00" * 100, 24000, 1, "voice:model")
    picks = Counter(_fillers("আমার ব্যালেন্স কত আছে?", n=2000, cache=cache))
    assert picks.most_common(1)[0][0] == cached
    # Preferred, not the only one.
    assert picks[cached] < 1000


def _template_lines() -> list[str]:
    return [
        *quick_reply._GENERIC_BN,
        *quick_reply._GENERIC_EN,
        *quick_reply._CORRECTION_BN,
        *quick_reply._CORRECTION_EN,
        *quick_reply._CHOICE_BN,
        *quick_reply._CHOICE_EN,
        *quick_reply._FOLLOW_UP_BN,
        *quick_reply._FOLLOW_UP_EN,
        *quick_reply._MORE_BN,
        *quick_reply._MORE_EN,
        *quick_reply._ACTION_BN,
        *quick_reply._ACTION_EN,
        *(
            line
            for topic in quick_reply._TOPIC_X
            for bangla in (True, False)
            for line in quick_reply._topic_lines(topic, bangla)
        ),
    ]


def test_template_lines_are_safe_short_and_telco():
    for line in _template_lines():
        # Always package, never pack.
        assert reply_punctuation.clean_reply_text(line) == line, line
        assert safe_filler(line, "") == line, line
        assert not real_estate_words(line), line
        # The filler prompt's own rule: no literary Bangla.
        assert not any(word in line for word in ("যাচাই", "মিলিয়ে", "ঘেঁটে", "খুলছি")), line
        assert quick_reply.is_filler_line(line)


def test_dekhchi_is_not_the_usual_verb():
    bangla = [line for line in _template_lines() if turn_gate.classify_script(line) == "bn"]
    assert sum("দেখছি" in line for line in bangla) * 4 <= len(bangla)
    for family in quick_reply._ECHO_BN.values():
        assert sum("দেখছি" in shape for shape in family) <= 1
        assert "দেখছি" not in family[0]
        assert len({quick_reply._opener(shape) for shape in family}) == len(family)


@pytest.mark.parametrize(
    "utterance",
    [
        "Show me fifteen day combo packs within my budget",
        "আমার বাজেটের মধ্যে পনেরো দিনের কম্বো প্যাক আছে?",
        "কারওয়ান বাজার এলাকায় কাছের কাস্টমার কেয়ার কোথায়?",
        "কারওয়ান বাজার এলাকায় নেট নাই",
    ],
)
def test_every_echo_of_the_longest_entities_fits(utterance):
    # Each shape passes safe_filler's word limit, so none is silently dropped.
    utterance = unicodedata.normalize("NFC", utterance)
    bangla = quick_reply._speaks_bangla(utterance, None)
    own_words = quick_reply._tiers(utterance, "packages", bangla)[0]
    assert len(own_words) == 5
    for line in own_words:
        assert safe_filler(line, utterance) == line, line


def test_only_filler_lines_are_cacheable():
    assert quick_reply.is_filler_line("জি, আপনার ব্যালেন্সটা চেক করে জানাচ্ছি")  # punctuation aside
    assert not quick_reply.is_filler_line("আপনার ব্যালেন্স ৫০ টাকা।")
    quick_reply.remember_filler("ওকে, আপনার প্যাকটা দেখছি।")
    assert quick_reply.is_filler_line("ওকে, আপনার প্যাকটা দেখছি।")


def test_ruled_out_validity_or_size_is_not_echoed():
    # From a call: "ত্রিশ দিন না" got "মাসিক ডাটা প্যাকেজগুলো".
    lines = _fillers(
        "আচ্ছা আমাকে ত্রিশ দিন না, আপনি এক দিনের কিছু package দেখান data।", n=40
    )
    assert all("এক দিনের" in line for line in lines)
    assert not any("মাসিক" in line for line in lines)
    assert quick_reply._size("২ জিবি না, ৫ জিবির প্যাকেজ") == ("৫ জিবির", "৫ GB")
    assert quick_reply._validity("not 30 days, a weekly one") == ("সাত দিনের", "weekly")


@pytest.mark.parametrize(
    ("utterance", "lines"),
    [
        ("আমি সর্বনিম্ন কত রিচার্জ করতে পারব?", quick_reply._RECHARGE_LIMIT_BN),
        ("সর্বোচ্চ কত টাকা রিচার্জ করা যায়?", quick_reply._RECHARGE_LIMIT_BN),
        ("বিকাশ দিয়ে কিভাবে রিচার্জ করব?", quick_reply._RECHARGE_HOW_BN),
        # Perks before how-to: it's about the cashback, not paying by bKash.
        ("বিকাশে রিচার্জ করলে ক্যাশব্যাক কত?", quick_reply._RECHARGE_PERKS_BN),
        ("১০০ টাকা রিচার্জ দিলাম, আসেনি", quick_reply._RECHARGE_STATUS_BN),
        ("What is the minimum recharge?", quick_reply._RECHARGE_LIMIT_EN),
    ],
)
def test_a_recharge_question_gets_the_lines_of_its_kind(utterance, lines):
    for line in set(_fillers(utterance, n=40)):
        assert line in lines, line


def test_a_recharge_request_still_gets_an_action_line():
    for line in set(_fillers("১০০ টাকা রিচার্জ করুন", n=40)):
        assert line in quick_reply._ACTION_BN, line


def test_a_new_kind_of_recharge_question_is_not_a_follow_up():
    last = quick_reply._RECHARGE_STATUS_BN[0]
    for line in set(_fillers("আচ্ছা, সর্বনিম্ন কত রিচার্জ করা যায়?", n=40, avoid=[last])):
        assert line in quick_reply._RECHARGE_LIMIT_BN, line


def test_recharge_kind_lines_are_safe_and_cacheable():
    sets = [
        quick_reply._RECHARGE_STATUS_BN, quick_reply._RECHARGE_LIMIT_BN,
        quick_reply._RECHARGE_HOW_BN, quick_reply._RECHARGE_PERKS_BN,
        quick_reply._RECHARGE_STATUS_EN, quick_reply._RECHARGE_LIMIT_EN,
        quick_reply._RECHARGE_HOW_EN, quick_reply._RECHARGE_PERKS_EN,
    ]
    for line in (line for lines in sets for line in lines):
        assert safe_filler(line, "রিচার্জ") == line, line
        assert quick_reply.is_filler_line(line), line


def test_how_much_taka_names_no_amount_but_an_amount_still_fails():
    assert safe_filler("বুঝেছি, কত টাকা রিচার্জ করা যায় দেখে জানাচ্ছি।", "সর্বনিম্ন কত রিচার্জ?")
    assert safe_filler("জি, পাঁচশো টাকার প্যাকেজ দেখে জানাচ্ছি।", "প্যাকেজ দেখান") is None


def test_a_recharge_question_about_the_process_is_how_to_not_status():
    # From a call: "process" got "রিচার্জটা ঠিকমতো হয়েছে কি না দেখে জানাচ্ছি".
    for line in set(_fillers("আমি actually recharge এর process টা সম্পর্কে জানতে চাচ্ছিলাম", n=40)):
        assert line in quick_reply._RECHARGE_HOW_BN, line


def test_a_recharge_question_of_no_known_kind_gets_a_generic_line():
    for line in set(_fillers("রিচার্জ নিয়ে একটা প্রশ্ন ছিল", n=40)):
        assert line in quick_reply._GENERIC_BN, line


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # From a call: "একটু সময় দিন, আমি জেনে বলছি।" before a question back.
        ("আ-আপনাদের কাছে কি কি প্যাকেজ আছে?", None),
        ("What packages do you have?", None),
        ("ডাটা প্যাকেজ কী আছে?", "filler"),
        ("৩ জিবির প্যাকেজ আছে?", "filler"),
        ("আরও প্যাকেজ দেখান", "filler"),
    ],
)
def test_a_broad_package_ask_gets_no_filler(text, expected):
    judgement = Judgement(0.9, "packages", 0.95)
    assert route(judgement, _Userdata(), _config(), _settings(), text=text) == expected
