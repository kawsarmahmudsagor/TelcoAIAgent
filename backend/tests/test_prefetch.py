"""The turn router's prefetch: an accepted turn's lookup runs before the LLM and
is handed to it as a tool call it made itself. The session, the extractor and
the tool cores are fakes; nothing touches the network or the database."""

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from livekit.agents import StopResponse, llm
from livekit.agents.llm import ToolError
from test_gated_session import _controller, _heard

from app.agent import entrypoint, prefetch
from app.agent.prefetch import Lookup, Prefetcher
from app.agent.turn_judge import Judgement
from app.agent.turn_router import RouterArgs
from app.config import Settings
from app.services import agent_config_service


class FakeSession:
    def __init__(self):
        self.userdata = SimpleNamespace()
        self.current_agent = SimpleNamespace(_chat_ctx=llm.ChatContext.empty())
        self.tool_items: list = []
        self._handlers: dict[str, list] = {}

    def on(self, event, handler):
        self._handlers.setdefault(event, []).append(handler)

    def off(self, event, handler):
        self._handlers[event].remove(handler)

    def emit(self, event, ev):
        for handler in list(self._handlers.get(event, [])):
            handler(ev)

    def _tool_items_added(self, items):
        self.tool_items.extend(items)

    def add_user_message(self, message):
        """What the library does once the reply is scheduled."""
        self.current_agent._chat_ctx.insert(message)
        self.emit("conversation_item_added", SimpleNamespace(item=message))


@pytest.fixture
def tools(monkeypatch):
    """The knowledge-base core, recording its calls."""
    calls: list[tuple[str, dict]] = []

    def search_text(query, config):
        calls.append(("knowledge_base", {"query": query}))
        return "Top results: the 5G plan costs 599 taka"

    monkeypatch.setattr(prefetch.search_knowledge_base, "search_text", search_text)
    return calls


def _prefetcher(monkeypatch, args: RouterArgs | None, **settings) -> tuple[Prefetcher, FakeSession]:
    async def extract(client, base_url, api_key, payload, timeout_s):
        return args

    monkeypatch.setattr(prefetch.turn_router, "extract", extract)
    session = FakeSession()
    config = agent_config_service.resolve(None)
    config.rag_enabled = True
    p = Prefetcher(
        session=session,
        settings=Settings(_env_file=None, router_enabled=True, **settings),
        config=config,
        api_key="or-key",
        client=None,
    )
    return p, session


def _msg(text: str) -> llm.ChatMessage:
    return llm.ChatMessage(role="user", content=[text])


def _run(p: Prefetcher, text: str, judgement: Judgement):
    turn_ctx = llm.ChatContext.empty()
    message = _msg(text)

    async def go():
        p.start(text, [])
        return await p.run(text, judgement, [], turn_ctx, message)

    lookups = asyncio.run(go())
    turn_ctx.insert(message)  # as pipeline_reply does
    return lookups, turn_ctx, message


_KB = RouterArgs(knowledge_query="5g plan price")
_KB_NAME = prefetch.search_knowledge_base.TOOL_NAME
_KB_ARGS = {"query": "5g plan price"}


def test_a_lookup_runs_before_the_llm_and_reads_as_its_own_tool_call(monkeypatch, tools):
    p, session = _prefetcher(monkeypatch, _KB)
    lookups, turn_ctx, message = _run(p, "5G plan koto?", Judgement(0.9, "knowledge_base", 0.98))

    assert tools == [("knowledge_base", _KB_ARGS)]
    assert [lookup.name for lookup in lookups] == [_KB_NAME]
    user, call, output = turn_ctx.items
    assert user is message
    assert call.type == "function_call" and call.name == _KB_NAME
    assert json.loads(call.arguments) == _KB_ARGS
    assert output.call_id == call.call_id and output.output.startswith("Top results")

    # The LLM sees one assistant message with the tool call, then its result.
    messages, _ = turn_ctx.to_provider_format("openai")
    assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
    assert messages[1]["tool_calls"][0]["function"]["name"] == _KB_NAME


def test_the_lookup_is_kept_only_once_the_reply_is_scheduled(monkeypatch, tools):
    p, session = _prefetcher(monkeypatch, _KB)
    stored: list = []
    p.on_prefetch = lambda message_id, name, args, output: stored.append((message_id, name, args))
    _, _, message = _run(p, "5G plan koto?", Judgement(0.9, "knowledge_base", 0.98))

    agent_ctx = session.current_agent._chat_ctx
    assert agent_ctx.items == [] and session.tool_items == [] and stored == []

    session.add_user_message(message)
    assert [item.type for item in agent_ctx.items] == ["message", "function_call", "function_call_output"]
    assert [item.type for item in session.tool_items] == ["function_call", "function_call_output"]
    assert stored == [(message.id, _KB_NAME, _KB_ARGS)]

    # One-shot: a later message doesn't add it again.
    session.add_user_message(_msg("next"))
    assert len(session.tool_items) == 2


def test_the_query_falls_back_to_the_customers_words(monkeypatch, tools):
    p, _ = _prefetcher(monkeypatch, RouterArgs())
    _run(p, "5G plan koto?", Judgement(0.9, "knowledge_base", 0.98))
    assert tools == [("knowledge_base", {"query": "5G plan koto?"})]


@pytest.mark.parametrize(
    ("args", "judgement"),
    [
        (_KB, Judgement(0.9, "none", 0.95)),  # no lookup needed
        (_KB, Judgement(0.9, "knowledge_base", 0.4)),  # Jev unsure
        (_KB, Judgement(0.9)),  # no lookup answer
        (_KB, Judgement(0.9, "listings", 0.98)),  # lookups of the old domain are gone
        (None, Judgement(0.9, "knowledge_base", 0.98)),  # extractor failed or timed out
    ],
)
def test_nothing_is_prefetched_when_the_router_cant_be_sure(monkeypatch, tools, args, judgement):
    p, session = _prefetcher(monkeypatch, args)
    routed: list = []
    p.on_routed = lambda *a: routed.append(a)
    lookups, turn_ctx, _ = _run(p, "5G plan koto?", judgement)
    assert lookups == [] and tools == []
    assert [item.type for item in turn_ctx.items] == ["message"]
    assert routed and routed[0][2] == []
    assert p._extracting == {}


def test_nothing_is_prefetched_when_the_knowledge_base_is_off(monkeypatch, tools):
    p, _ = _prefetcher(monkeypatch, _KB)
    p.config.rag_enabled = False
    lookups, _, _ = _run(p, "5G plan koto?", Judgement(0.9, "knowledge_base", 0.98))
    assert lookups == [] and tools == []


def test_a_query_the_tool_refuses_leaves_it_to_the_llm(monkeypatch):
    def refuse(query, config):
        raise ToolError("bad query")

    monkeypatch.setattr(prefetch.search_knowledge_base, "search_text", refuse)
    p, _ = _prefetcher(monkeypatch, _KB)
    lookups, turn_ctx, _ = _run(p, "5G plan koto?", Judgement(0.9, "knowledge_base", 0.98))
    assert lookups == []
    assert [item.type for item in turn_ctx.items] == ["message"]


def test_a_new_final_cancels_the_stale_extraction(monkeypatch):
    started = asyncio.Event()

    async def slow(client, base_url, api_key, payload, timeout_s):
        started.set()
        await asyncio.sleep(10)

    monkeypatch.setattr(prefetch.turn_router, "extract", slow)
    p, _ = _prefetcher(monkeypatch, None)
    monkeypatch.setattr(prefetch.turn_router, "extract", slow)

    async def go():
        p.start("মোহাম্মদপুরের দিকে", [])
        first = p._extracting["মোহাম্মদপুরের দিকে"]
        await started.wait()
        p.start("মোহাম্মদপুরের দিকে অফারসহ ফ্ল্যাট আছে?", [])
        await asyncio.sleep(0)
        assert first.cancelled()
        assert list(p._extracting) == ["মোহাম্মদপুরের দিকে অফারসহ ফ্ল্যাট আছে"]
        p.cancel()

    asyncio.run(go())


def test_warm_up_opens_the_router_and_jev_connections_once():
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path.endswith("/chat/completions"):
            content = json.dumps(
                {"search": {}, "offers": {}, "knowledge_query": None}
            )
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
        return httpx.Response(200, json={"data": {}})

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            p = Prefetcher(
                session=FakeSession(),
                settings=Settings(_env_file=None, router_enabled=True),
                config=agent_config_service.resolve(None),
                api_key="or-key",
                client=client,
            )
            p.warm()
            p.warm()  # a second call starts nothing new
            await p._warming

    asyncio.run(go())
    assert sorted(requests) == ["/api/v1/chat/completions", "/api/v1/key"]


def test_warm_up_failures_stay_quiet():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            p = Prefetcher(
                session=FakeSession(),
                settings=Settings(_env_file=None, router_enabled=True),
                config=agent_config_service.resolve(None),
                api_key="or-key",
                client=client,
            )
            p.warm()
            await p._warming

    asyncio.run(go())


# ---- the gate drives it ----


class FakePrefetcher:
    def __init__(self):
        self.started: list[str] = []
        self.ran: list[tuple[str, Judgement]] = []
        self.cancelled = 0

    def start(self, text, history):
        self.started.append(text)

    def cancel(self):
        self.cancelled += 1

    async def run(self, text, judgement, history, turn_ctx, new_message):
        self.ran.append((text, judgement))
        return [Lookup(_KB_NAME, {}, "Found", 0.01)]


def test_the_gate_starts_the_router_with_jev_and_runs_it_on_an_accepted_turn():
    async def go():
        gate, _, _, _ = _controller(0.8)
        gate.prefetcher = FakePrefetcher()
        _heard(gate, "What about Uttara?")
        await gate.on_user_turn_completed(_msg("What about Uttara?"), llm.ChatContext.empty())
        assert gate.prefetcher.started == ["What about Uttara?"]
        assert [text for text, _ in gate.prefetcher.ran] == ["What about Uttara?"]

    asyncio.run(go())


def test_a_dropped_turn_never_runs_a_lookup():
    async def go():
        gate, _, _, _ = _controller(0.1)
        gate.prefetcher = FakePrefetcher()
        _heard(gate, "আম্মু, এটা তো অনেক দামি।")
        with pytest.raises(StopResponse):
            await gate.on_user_turn_completed(
                _msg("আম্মু, এটা তো অনেক দামি।"), llm.ChatContext.empty()
            )
        assert gate.prefetcher.ran == []
        assert gate.prefetcher.cancelled >= 1

    asyncio.run(go())


def test_router_only_with_an_openrouter_llm():
    config = agent_config_service.resolve(None)
    on = Settings(_env_file=None, router_enabled=True)
    config.llm_provider = "openrouter"
    assert entrypoint._router_enabled(on, config)
    config.llm_provider = "gemini"  # Gemini 3 rejects a tool call it didn't make
    assert not entrypoint._router_enabled(on, config)
    config.llm_provider = "openrouter"
    assert not entrypoint._router_enabled(Settings(_env_file=None, router_enabled=False), config)
