"""Runs the turn router's lookups before the LLM and hands it their results.

For a finished, accepted listening turn the gate knows (from Jev) which lookup
the reply needs and (from app.agent.turn_router) its arguments. Running it here
and putting the call and its result into the turn's chat context, exactly as if
the LLM had called the tool, leaves the LLM one round trip instead of two. The
LLM keeps every tool, so when the router is unsure, slow or wrong it just calls
them itself, as it does without the router.

The injected call and result are also written to the agent's chat context once
the turn's user message is (only if the reply is scheduled), so later turns
still see the lookup results.
"""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from livekit.agents import AgentSession, llm
from livekit.agents.llm import ToolError

from app.agent import turn_gate, turn_router
from app.agent.tools import care_centres, search_knowledge_base
from app.agent.tools.packages import run_search_packages
from app.agent.turn_judge import Exchange, Judgement
from app.agent.turn_router import RouterArgs
from app.bss.errors import BssError
from app.config import Settings
from app.services.agent_config_service import ResolvedAgentConfig

logger = logging.getLogger("agent.prefetch")

# Nobody waits on the warm-up, so it may take as long as a cold start needs.
_WARM_TIMEOUT_S = 10.0

# What each lookup runs.
_LOOKUP_TOOLS = {
    "packages": ("search_packages",),
    "knowledge_base": (search_knowledge_base.TOOL_NAME,),
    "care_centre": (care_centres.TOOL_NAME,),
}


@dataclass(frozen=True)
class Lookup:
    """One tool run for the LLM: what it was called with and what it returned."""

    name: str
    args: dict
    output: str
    seconds: float


@dataclass
class Prefetcher:
    """Per-session router state: the extractor calls started on STT finals, and
    the settings to run lookups with."""

    session: AgentSession
    settings: Settings
    config: ResolvedAgentConfig
    api_key: str
    client: httpx.AsyncClient
    # (lookup, lookup_p, lookups run, seconds) for every routed turn (run_log).
    on_routed: Callable[[str | None, float | None, list[Lookup], float], None] | None = None
    # (user message id, tool name, args, output) for every lookup injected, once
    # its turn is kept (the stored transcript).
    on_prefetch: Callable[[str, str, dict | None, str | None], None] | None = None
    _extracting: dict[str, asyncio.Task[RouterArgs | None]] = field(default_factory=dict)
    # The fast rules' arguments for the same text (turn_router.fast_extract), or None.
    _fast: dict[str, RouterArgs | None] = field(default_factory=dict)
    _warming: asyncio.Task | None = None

    # ---- warm-up, while the greeting plays ----

    def warm(self) -> None:
        """Opens the connections the first turn's Jev and router calls will use.
        run_3's first router call paid for a new connection and the provider's
        cold start, and hit the 1.5 s timeout. One throwaway extraction warms
        both; a tiny request alongside it opens a second connection, since Jev
        and the router run at the same time."""
        if self._warming is None:
            self._warming = asyncio.ensure_future(self._warm())

    async def _warm(self) -> None:
        base_url = self.settings.openrouter_base_url
        payload = turn_router.build_request(
            self.settings.router_model, [], "hello", self.settings.router_reasoning_effort
        )
        await asyncio.gather(
            turn_router.extract(self.client, base_url, self.api_key, payload, _WARM_TIMEOUT_S),
            self._ping(base_url),
        )

    async def _ping(self, base_url: str) -> None:
        try:
            await self.client.get(
                f"{base_url.rstrip('/')}/key",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=_WARM_TIMEOUT_S,
            )
        except Exception as exc:
            logger.info("router warm-up request failed: %s", exc)

    # ---- the extractor, started alongside Jev ----

    def start(self, text: str, history: list[Exchange]) -> None:
        """Starts extracting arguments for `text` (cached by its words). Calls for
        other text are stale -- the turn grew or moved on -- and are cancelled."""
        key = turn_gate.normalize(text)
        if not key or key in self._extracting:
            return
        self.cancel()
        payload = turn_router.build_request(
            self.settings.router_model,
            history,
            text,
            self.settings.router_reasoning_effort,
        )
        self._fast[key] = turn_router.fast_extract(text, history)
        self._extracting[key] = asyncio.ensure_future(
            turn_router.extract(
                self.client,
                self.settings.openrouter_base_url,
                self.api_key,
                payload,
                self.settings.router_timeout_ms / 1000,
            )
        )

    def cancel(self) -> None:
        for task in self._extracting.values():
            task.cancel()
        self._extracting.clear()
        self._fast.clear()

    # ---- an accepted turn ----

    async def run(
        self,
        text: str,
        judgement: Judgement,
        history: list[Exchange],
        turn_ctx: llm.ChatContext,
        new_message: llm.ChatMessage,
    ) -> list[Lookup]:
        """Runs the lookup the turn needs and injects it into turn_ctx. Returns
        what was injected (nothing when the router is unsure or anything fails)."""
        started = time.perf_counter()
        lookups: list[Lookup] = []
        try:
            lookups = await self._lookups(text, judgement, history)
            if lookups:
                self._inject(lookups, turn_ctx, new_message)
        except Exception:
            # Raising here would make the library drop the customer's turn.
            logger.exception("prefetch failed; the LLM will call the tools itself")
            lookups = []
        finally:
            self.cancel()
        if self.on_routed is not None:
            self.on_routed(
                judgement.lookup, judgement.lookup_p, lookups, time.perf_counter() - started
            )
        return lookups

    async def _lookups(
        self, text: str, judgement: Judgement, history: list[Exchange]
    ) -> list[Lookup]:
        tools = _LOOKUP_TOOLS.get(judgement.lookup or "none")
        if not tools or (judgement.lookup_p or 0.0) < self.settings.router_min_p:
            return []
        if judgement.lookup == "knowledge_base" and not self.config.rag_enabled:
            return []

        key = turn_gate.normalize(text)
        if key not in self._extracting:
            # The library's turn text differs from the finals the gate saw.
            self.start(text, history)
        fast = self._fast.get(key) if judgement.lookup == "packages" else None
        if fast is not None:
            # A plain package request: the rules give the extractor's arguments
            # without waiting for it. Every other lookup waits, as before.
            logger.info("router: fast rules gave %s", fast.packages)
            args = fast
        else:
            args = await self._extracting[key]
        if args is None:
            return []

        lookups = []
        for name in tools:
            lookup = await self._run_tool(name, args, text)
            if lookup is not None:
                lookups.append(lookup)
        return lookups

    async def _run_tool(self, name: str, args: RouterArgs, text: str) -> Lookup | None:
        started = time.perf_counter()
        try:
            if name == "search_packages":
                call_args = dict(args.packages)
                # The tool's own run: it also puts the package cards on screen.
                output = await run_search_packages(self.session.userdata, **call_args)
            elif name == care_centres.TOOL_NAME:
                # No place named: the tool falls back to the customer's district.
                call_args = {"place": args.care_place} if args.care_place else {}
                output = await care_centres.run_find_care_centre(
                    self.session.userdata, args.care_place
                )
            else:
                call_args = {"query": args.knowledge_query or text}
                output = await asyncio.to_thread(
                    search_knowledge_base.search_text, call_args["query"], self.config
                )
        except (ToolError, BssError) as exc:
            # Arguments the tool refuses: the LLM gets to call it itself.
            logger.info("prefetch %s refused %s: %s", name, args, exc)
            return None
        return Lookup(name, call_args, output, time.perf_counter() - started)

    def _inject(
        self, lookups: list[Lookup], turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        """The calls, then their outputs, right after the user message: one
        assistant message with parallel tool calls, as the LLM would have made."""
        group_id = f"prefetch_{uuid.uuid4().hex[:12]}"
        at = new_message.created_at
        calls, outputs = [], []
        for i, lookup in enumerate(lookups):
            call_id = f"{group_id}_{i}"
            calls.append(
                llm.FunctionCall(
                    call_id=call_id,
                    name=lookup.name,
                    arguments=json.dumps(lookup.args, ensure_ascii=False),
                    group_id=group_id,
                    created_at=at + 0.001 * (i + 1),
                )
            )
            outputs.append(
                llm.FunctionCallOutput(
                    call_id=call_id,
                    name=lookup.name,
                    output=lookup.output,
                    is_error=False,
                    created_at=at + 0.001 * (len(lookups) + i + 1),
                )
            )
        items = [*calls, *outputs]
        turn_ctx.insert(items)
        self._persist_after(new_message, items, lookups)

    def _persist_after(
        self, new_message: llm.ChatMessage, items: list, lookups: list[Lookup]
    ) -> None:
        """turn_ctx is a copy for this reply only. The library adds the user
        message to the agent's chat context only if the reply is scheduled; the
        lookups follow it there (and into the transcript) at that moment, so a
        dropped reply never leaves a tool call without its question."""
        session = self.session

        def _on_item(ev) -> None:
            if getattr(ev.item, "id", None) != new_message.id:
                return
            session.off("conversation_item_added", _on_item)
            agent = session.current_agent
            agent._chat_ctx.insert(items)
            session._tool_items_added(items)
            if self.on_prefetch is not None:
                for lookup in lookups:
                    self.on_prefetch(new_message.id, lookup.name, lookup.args, lookup.output)

        session.on("conversation_item_added", _on_item)
