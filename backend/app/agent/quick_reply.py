"""Quick replies: a small, fast model makes a gated voice call feel quicker.

Jev already says which lookup each finished turn needs (turn_judge.LOOKUP_KEY).
That one answer picks the path (route):

- "fast": no lookup is needed (a greeting, thanks, a question about what was
  already said), so the small model answers the turn itself. It sees the whole
  conversation and the same instructions, plus FAST_RULES, and has no tools but
  end_call. When the turn needs anything it can't answer from the conversation
  it writes HANDOFF and nothing else, and the main model answers instead
  (stream_fast hands off without a word of it spoken).
- "filler": a lookup is needed, so the small model writes one short line ("let
  me find those for you") that is spoken until the main model's reply starts
  (compose_filler): while the search runs, and after it in front of the reply
  if the line is ready before the reply's first words, else dropped. The line
  states no facts: safe_filler drops one with numbers, money or contact details
  the customer didn't say.

Anything less sure stays on the main model, as without quick replies.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

import httpx
from livekit.agents import APIConnectOptions, llm
from livekit.agents.voice.generation import INSTRUCTIONS_MESSAGE_ID

from app.agent import turn_gate
from app.agent.quick_models import reasoning_for
from app.agent.turn_judge import Exchange, Judgement
from app.config import Settings
from app.services.agent_config_service import ResolvedAgentConfig

logger = logging.getLogger("agent.quick_reply")
usage_logger = logging.getLogger("agent.usage")

Route = Literal["fast", "filler"]

# The small model's way of saying "the main model should answer this".
HANDOFF = "[[MAIN]]"

FILLER_MAX_WORDS = 10
# How many earlier lines the filler is told not to repeat.
_AVOID = 5

_NUMBER_RE = re.compile(r"\d+")  # Bangla digits too
_MONEY_RE = re.compile(r"৳|\$|\btk\b|taka|টাকা|\blakh|\bcrore|লাখ|লক্ষ|কোটি", re.IGNORECASE)
# A phone number (seven or more digits, spaces and dashes allowed) or an email.
_CONTACT_RE = re.compile(r"\+?\d(?:[\s-]?\d){6,}|\S+@\S+\.\w+")

FAST_RULES = f"""

# Quick answer mode
You are answering this one turn quickly, from the conversation alone, with no tools except end_call.
Reply in the language of the customer's latest message (LANGUAGE above), whatever earlier turns used.
When the customer wraps up or says goodbye (also informally: tata, bye bye, আসি তাহলে, রাখি তাহলে,
ভালো থাকবেন), follow the instructions above for ending the call.
Answer only when everything you need was already said in this conversation or is in the instructions above:
greetings, thanks, small talk, goodbyes, or repeating or explaining something already said.
Reply with exactly {HANDOFF} and nothing else when the customer:
- asks for any balance, pack, usage, price, offer, validity or policy fact not already said;
- asks again for their own balance, data, minutes, points or usage (it may have changed);
- wants to buy a pack, recharge, redeem an offer or open a case, or gives a number to recharge;
- says a code of 4 to 8 digits (an OTP), in any language or script;
- complains about the network, a charge or the service;
- asks for a follow-up or a call back;
- asks anything you are not sure you can answer from the conversation.
Never guess a fact. When in doubt, reply with exactly {HANDOFF}."""

_FILLER_SYSTEM = """You write the line a mobile operator's phone assistant says the moment a customer \
finishes speaking, while the full answer is still being looked up by someone else. It is spoken aloud.
Write one short, warm, natural spoken sentence (under 8 words) that fits this request and tells the \
customer you are on it. Vary it: pick a different style each time, whichever suits the request:
- echo what they asked for ("ইন্টারনেট প্যাক, ওকে।", "Data packs. Okay.");
- a short reaction and the next step ("ঠিক আছে, আমি দেখছি।", "ওকে, প্যাকগুলো দেখছি।", \
"Okay, checking that now.");
- a plain, warm wait ("জি, এক মিনিট।", "অবশ্যই, একটু চেক করছি।", "জি, একটু ওয়েট করুন।", \
"Sure, one moment.");
- a professional, to-the-point line ("Checking your account.", "ব্যালেন্সটা চেক করছি।", \
"প্যাকগুলো দেখছি।");
- by request type: a balance or usage question says so ("ব্যালেন্সটা চেক করছি।"); a pack search \
names what they want ("ডাটা প্যাকগুলো দেখছি।"); a price or offer question says so ("দামটা চেক করছি।", \
"অফারগুলো দেখছি।"); a policy question stays simple ("ঠিক আছে, আমি দেখছি।").
Language: the language of the customer's NEW message alone. Bangla (in Bengali script or written in \
Latin letters) gets a Bangla line in Bengali script, in the respectful আপনি form, in the way people \
actually speak, not a word-for-word translation. Use everyday English words in Bengali script where \
Bangla speakers do (চেক, প্যাক, ব্যালেন্স, ওকে, ওয়েট); say "দাম", not "প্রাইস". Never use literary \
Bangla words such as মিলিয়ে, যাচাই, ঘেঁটে, খুলছি. When you echo an amount or a number the customer \
said, say it in the customer's language: Bangla words for Bangla ("তিনশো টাকার মধ্যে, ওকে।"), English \
words for English. English gets an English line.
Never state a price, a number, a balance, availability, or a result of your own (only echo what the \
customer said), and never describe how many or how good the results are (nothing is found yet; there \
may be none). Never answer the question; never promise an outcome; never say a person is joining. \
No greeting, no question, no emoji.
Don't repeat any of the lines listed as already said, nor their verb or sentence shape.
Reply with JSON only: {"text": "..."}"""


@dataclass
class QuickReplyRuntime:
    """One session's quick-reply state: the config switches, the OpenRouter
    connection, and the filler lines said so far."""

    config: ResolvedAgentConfig
    settings: Settings
    api_key: str
    client: httpx.AsyncClient
    said: list[str] = field(default_factory=list)
    # What the small model is doing, for the run log: "asked", "wrote ...", "timed out".
    on_event: Callable[[str], None] | None = None
    _fast_llm: llm.LLM | None = None

    @property
    def fast_answer(self) -> bool:
        return self.config.quick_reply_enabled and self.config.quick_fast_answer

    @property
    def filler(self) -> bool:
        return self.config.quick_reply_enabled and self.config.quick_filler

    def fast_llm(self) -> llm.LLM:
        """Built on first use, so a call that never takes the fast path never
        opens its connection."""
        if self._fast_llm is None:
            self._fast_llm = build_fast_llm(self.config, self.settings, self.api_key)
        return self._fast_llm

    def avoid(self, utterance: str) -> list[str]:
        """The last lines said in the utterance's script: a line in the other
        language would pull the new one toward it."""
        script = turn_gate.classify_script(utterance)
        return [line for line in self.said if turn_gate.classify_script(line) == script][-_AVOID:]

    async def compose(
        self, utterance: str, lookup: str | None, history: list[Exchange]
    ) -> str | None:
        return await compose_filler(
            self.client,
            self.settings.openrouter_base_url,
            self.api_key,
            self.config.quick_reply_model,
            utterance,
            lookup,
            history,
            self.avoid(utterance),
            timeout_s=self.settings.filler_timeout_ms / 1000,
            on_event=self.on_event,
        )


def quick_on(config: ResolvedAgentConfig) -> bool:
    return config.quick_reply_enabled and (config.quick_fast_answer or config.quick_filler)


def route(
    judgement: Judgement | None,
    userdata: object,
    config: ResolvedAgentConfig,
    settings: Settings,
    *,
    closing: bool = False,
) -> Route | None:
    """Which quick path an accepted turn takes; None = the main model, as
    without quick replies. closing: the gate took the turn as a goodbye
    (turn_gate.is_closing) without asking Jev -- it needs no lookup, and ending
    the call is the one tool the small model has."""
    if not config.quick_reply_enabled:
        return None
    # An OTP or a yes/no for a waiting action, or a case being drafted, belongs to
    # the main model, which owns the tools; Jev may well say "none" for it.
    if getattr(userdata, "pending_action", None) or getattr(userdata, "pending_case", None):
        return None
    if closing:
        if config.quick_fast_answer:
            return "fast"
        return None
    if judgement is None or judgement.lookup is None:
        return None
    lookup_p = judgement.lookup_p or 0.0
    if judgement.lookup == "none":
        if config.quick_fast_answer and lookup_p >= settings.quick_route_min_p:
            return "fast"
        return None
    # A weak guess at a search gets no "let me find that": the main model may
    # well ask a question instead.
    if config.quick_filler and lookup_p >= settings.router_min_p:
        return "filler"
    return None


def build_fast_llm(config: ResolvedAgentConfig, settings: Settings, api_key: str) -> llm.LLM:
    from livekit.plugins import openai

    return openai.LLM(
        model=config.quick_reply_model,
        api_key=api_key,
        base_url=settings.openrouter_base_url,
        temperature=config.temperature,
        max_completion_tokens=config.max_output_tokens,
        extra_body={"reasoning": reasoning_for(config.quick_reply_model)},
    )


def end_call_tools(tools: Sequence[llm.Tool]) -> list[llm.Tool]:
    """A new list with only the end_call tool: the caller's list is synced back
    into the turn's tools by the library, so it must not change."""
    return [tool for tool in tools if isinstance(tool, llm.FunctionTool) and tool.id == "end_call"]


def fast_chat_ctx(chat_ctx: llm.ChatContext) -> llm.ChatContext:
    """The conversation for the small model: the agent's instructions plus
    FAST_RULES, without tool calls (fewer tokens, and no other model's tool
    calls for it to choke on). copy() is shallow, so the instructions message is
    replaced, never changed in place -- that would put FAST_RULES into the main
    model's prompt for the rest of the call."""
    ctx = chat_ctx.copy(exclude_function_call=True)
    idx = ctx.index_by_id(INSTRUCTIONS_MESSAGE_ID)
    if idx is not None and ctx.items[idx].type == "message":
        old = ctx.items[idx]
        ctx.items[idx] = llm.ChatMessage(
            id=INSTRUCTIONS_MESSAGE_ID,
            role="system",
            content=[(old.text_content or "") + FAST_RULES],
            created_at=old.created_at,
        )
    else:
        ctx.items.insert(
            0, llm.ChatMessage(id=INSTRUCTIONS_MESSAGE_ID, role="system", content=[FAST_RULES])
        )
    return ctx


class Handoff(Exception):
    """The small model can't answer this turn: the main model should."""


async def stream_fast(
    fast_llm: llm.LLM,
    chat_ctx: llm.ChatContext,
    tools: Sequence[llm.Tool],
    *,
    buffer_chars: int,
    first_chunk_timeout_s: float,
) -> AsyncIterator[llm.ChatChunk | str]:
    """The small model's answer. Raises Handoff before yielding anything when it
    writes HANDOFF, fails, is too slow to start, or says nothing. The first
    buffer_chars are held back so a HANDOFF is never spoken; once text has gone
    out a later error just ends the answer."""
    held = ""
    yielded = False
    try:
        async with fast_llm.chat(
            chat_ctx=chat_ctx, tools=list(tools), conn_options=APIConnectOptions(max_retry=0)
        ) as stream:
            chunks = stream.__aiter__()
            first = True
            while True:
                try:
                    if first:
                        async with asyncio.timeout(first_chunk_timeout_s):
                            chunk = await chunks.__anext__()
                        first = False
                    else:
                        chunk = await chunks.__anext__()
                except StopAsyncIteration:
                    break
                delta = chunk.delta
                if delta is None:
                    continue
                if delta.tool_calls:
                    if HANDOFF in held:
                        raise Handoff()
                    if held:
                        yield held.replace(HANDOFF, "")
                        held = ""
                    yielded = True
                    yield chunk
                    continue
                text = delta.content or ""
                if not text:
                    continue
                if yielded:
                    out, held = _split_marker_tail((held + text).replace(HANDOFF, ""))
                    if out:
                        yield out
                    continue
                held += text
                if HANDOFF in held:
                    raise Handoff()
                if len(held) >= buffer_chars:
                    # A HANDOFF cut in two stays held until the rest shows it.
                    out, held = _split_marker_tail(held)
                    if out:
                        yielded = True
                        yield out
    except Handoff:
        raise
    except Exception as exc:
        if not yielded:
            raise Handoff() from exc
        logger.warning("fast answer stopped early: %s", exc)
        return
    if not yielded:
        if HANDOFF in held or not held.strip():
            raise Handoff()
    if held:
        yield held


def _split_marker_tail(text: str) -> tuple[str, str]:
    """(text to say, a trailing start of HANDOFF to hold back)."""
    for size in range(min(len(HANDOFF) - 1, len(text)), 0, -1):
        if text.endswith(HANDOFF[:size]):
            return text[:-size], text[-size:]
    return text, ""


def safe_filler(text: str, utterance: str) -> str | None:
    """The line, if it is one: short, and stating no number, price or contact of
    its own (which could only be a guess -- nothing has been looked up yet).
    Numbers the customer said may be echoed."""
    text = " ".join(text.split())
    if not text or len(text.split()) > FILLER_MAX_WORDS:
        return None
    if _CONTACT_RE.search(text):
        return None
    if not set(_NUMBER_RE.findall(text)) <= set(_NUMBER_RE.findall(utterance)):
        return None
    if _MONEY_RE.search(text) and not _MONEY_RE.search(utterance):
        return None
    if text.rstrip().endswith(("?", "？")):
        return None
    return text


def build_filler_request(
    model: str,
    utterance: str,
    lookup: str | None,
    history: list[Exchange],
    avoid: list[str],
) -> dict:
    lines = ["Conversation so far:"]
    lines += [f"{'Customer' if e.role == 'user' else 'Assistant'}: {e.text}" for e in history]
    if not history:
        lines.append("(none yet)")
    if lookup:
        lines.append(f"What is being looked up: {lookup.replace('_', ' ')}.")
    if avoid:
        lines.append("Already said (don't repeat): " + " | ".join(avoid))
    lines.append(f"Customer's new message: {utterance}")
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _FILLER_SYSTEM},
            {"role": "user", "content": "\n".join(lines)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 120,
        "reasoning": reasoning_for(model),
        # Customer speech: keep it out of provider training data.
        "provider": {"sort": "latency", "data_collection": "deny"},
    }


async def compose_filler(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    utterance: str,
    lookup: str | None,
    history: list[Exchange],
    avoid: list[str],
    *,
    timeout_s: float,
    on_event: Callable[[str], None] | None = None,
) -> str | None:
    """A filler line for the turn, or None on any error, timeout or unsafe line."""
    payload = build_filler_request(model, utterance, lookup, history, avoid)
    started = time.perf_counter()

    def note(text: str) -> None:
        if on_event is not None:
            on_event(f"filler: {text}")

    note(f"asking {model} for a line")
    try:
        response = await asyncio.wait_for(
            client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            ),
            timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        cost = usage.get("cost")
        usage_logger.info(
            "Filler %s: %s input tokens, %s output, $%s, %dms",
            body.get("model") or model,
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            f"{cost:.6f}" if isinstance(cost, (int, float)) else "?",
            (time.perf_counter() - started) * 1000,
        )
        text = json.loads(content)["text"]
    except (TimeoutError, asyncio.TimeoutError):
        logger.info("filler timed out after %.2fs", timeout_s)
        note(f"{model} timed out after {timeout_s:.2f} s, no line")
        return None
    except Exception as exc:
        logger.warning("filler failed: %s", exc)
        note(f"{model} failed ({exc}), no line")
        return None
    took = time.perf_counter() - started
    line = safe_filler(text, utterance) if isinstance(text, str) else None
    if line is None:
        logger.info("filler dropped: %r", text)
        note(f'{model} wrote "{text}" in {took:.2f} s, dropped (unsafe or too long)')
    else:
        note(f'{model} wrote "{line}" in {took:.2f} s')
    return line
