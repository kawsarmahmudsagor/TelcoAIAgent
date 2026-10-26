"""Relevance judge for voice turns: is this utterance addressed to the agent?

Asks TypeSafe's Jev decision model (via OpenRouter's Decisions API) one yes/no
("noul") question and returns the probability of yes. Jev returns typed answers
only, so there is nothing to parse; any failure returns None, which callers
treat as "accept" -- ignoring a real customer costs more than answering noise.

Kept free of livekit imports so scripts/judge_bench can drive the exact request
the agent sends.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Literal

import httpx

logger = logging.getLogger(__name__)
# Same logger as app.agent.usage_log, so all provider usage lines filter together.
usage_logger = logging.getLogger("agent.usage")

BotState = Literal["listening", "speaking", "thinking"]

QUESTION_KEY = "addressed"
# The turn router's question (app.agent.turn_router), asked in the same request:
# which lookup the reply will need, so it can run before the LLM.
LOOKUP_KEY = "lookup"

_INSTRUCTIONS = (
    "A mobile operator's voice assistant is in a live call with a customer in Bangladesh. "
    "The microphone also picks up other people in the room and background audio (TV, "
    "chatter). Decide whether the latest utterance is the customer speaking to the "
    "assistant about their mobile service, given the recent conversation. "
    "Customers speak English or Bangla, and may ask whether the assistant can hear them "
    "(শুনতে পাচ্ছ, শুনতে পাচ্ছেন, hello, can you hear me). Short answers to the "
    "assistant's last question (a number, a code, yes/no, a package name) count, and so "
    "does someone reading out a 4 to 8 digit code. "
    "Requests on other topics (sports, news, weather, politics, general knowledge) do not "
    "count, even when asked to the assistant directly."
)

_CRITERIA = {
    "true": (
        "The customer is talking to the assistant about their mobile service: answering its "
        "question or reading out a code, asking about balance, packages, usage, offers, "
        "recharge, a complaint or the operator, asking whether the assistant can hear them "
        "(hello, are you there, শুনতে পাচ্ছেন, কথা শুনতে পাচ্ছেন), correcting it, asking it to "
        "wait, stop or repeat, or a brief greeting, thanks or goodbye."
    ),
    "false": (
        "Someone talking to another person in the room, TV or radio audio, a request about "
        "an unrelated topic (sports, news, weather, politics, trivia), speech in a language "
        "other than English or Bangla, or garbled fragments that carry no request."
    ),
}


_LOOKUP_INSTRUCTIONS = (
    "Which lookup does the assistant need before it can answer the latest utterance? "
    "Pick packages only when the customer asks what packs exist or gives what they want "
    "in a pack (data, minutes, price, validity). Questions about their own account "
    "(balance, usage, current pack) are answered from the account snapshot or by the "
    "assistant's own tools, so they need no lookup here. Buying, recharging, redeeming, "
    "reading out a code, filing a complaint, greetings and thanks need no lookup either."
)

_LOOKUP_CRITERIA = {
    "packages": (
        "Search the operator's packages: the customer asks what packs are available, or "
        "gives or changes what they want (data amount, minutes, price, validity)."
    ),
    "knowledge_base": (
        "A question about the operator, its policies, coverage, fees or how a service "
        "works, not about the customer's own account."
    ),
    "none": (
        "No lookup: a question about the customer's own account (balance, usage, current "
        "pack, offers), a purchase, recharge, redeem or complaint request, a code being "
        "read out, a greeting, thanks, goodbye, or anything else."
    ),
}


@dataclass(frozen=True)
class Judgement:
    """Jev's answers for one utterance. p = P(addressed), None when the call failed
    or timed out. lookup / lookup_p only when the lookup question was asked."""

    p: float | None
    lookup: str | None = None
    lookup_p: float | None = None
    text: str | None = None


@dataclass(frozen=True)
class Exchange:
    role: Literal["user", "assistant"]
    text: str


def decisions_url(openrouter_base_url: str) -> str:
    """OpenRouter's Decisions API sits beside /api/v1, under /api/alpha."""
    base = openrouter_base_url.rstrip("/")
    if base.endswith("/api/v1"):
        base = base[: -len("/api/v1")]
    return f"{base}/api/alpha/decisions"


def build_state(
    history: list[Exchange],
    utterance: str,
    bot_state: BotState,
    address_form: str | None = None,
) -> str:
    lines = ["Recent conversation:"]
    lines += [f"{'Customer' if e.role == 'user' else 'Assistant'}: {e.text}" for e in history]
    if not history:
        lines.append("(none yet)")
    activity = {
        "listening": "waiting for the customer",
        "speaking": "speaking",
        "thinking": "looking something up",
    }[bot_state]
    lines.append(f"While the assistant was {activity}, the microphone picked up: {utterance!r}")
    if address_form:
        lines.append(f"Form of address used in the utterance: {address_form}")
    return "\n".join(lines)


def lookup_question(knowledge_base: bool) -> dict:
    criteria = dict(_LOOKUP_CRITERIA)
    if not knowledge_base:
        criteria.pop("knowledge_base")
    return {"type": "choice", "instructions": _LOOKUP_INSTRUCTIONS, "criteria": criteria}


def build_request(
    model: str,
    history: list[Exchange],
    utterance: str,
    bot_state: BotState,
    address_form: str | None = None,
    *,
    lookup: bool = False,
    knowledge_base: bool = False,
) -> dict:
    """lookup adds the router's choice question (knowledge_base: whether that's
    an option)."""
    questions: dict = {
        QUESTION_KEY: {
            "type": "noul",
            "instructions": _INSTRUCTIONS,
            "criteria": _CRITERIA,
        }
    }
    if lookup:
        questions[LOOKUP_KEY] = lookup_question(knowledge_base)
    return {
        "model": model,
        "state": build_state(history, utterance, bot_state, address_form),
        "questions": questions,
        # Customer speech: keep it out of provider training data.
        "provider": {"data_collection": "deny"},
    }


async def judge(
    client: httpx.AsyncClient,
    url: str,
    api_key: str,
    payload: dict,
    timeout_s: float,
    utterance: str | None = None,
) -> Judgement:
    """P(addressed) in [0, 1] (None on any error or timeout), plus the lookup
    choice when the request asked for it."""
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            client.post(url, json=payload, headers={"Authorization": f"Bearer {api_key}"}),
            timeout_s,
        )
        response.raise_for_status()
        body = response.json()
        answers = body["answers"]
        p = min(1.0, max(0.0, float(answers[QUESTION_KEY]["noul"])))
        lookup, lookup_p = _lookup_answer(answers.get(LOOKUP_KEY))
        usage = body.get("usage") or {}
        cost = usage.get("cost")
        usage_logger.info(
            "Jev %s: %s input tokens, $%s, %dms, P=%.2f%s",
            body.get("model") or payload.get("model"),
            usage.get("input_tokens", "?"),
            f"{cost:.6f}" if isinstance(cost, (int, float)) else "?",
            (time.perf_counter() - started) * 1000,
            p,
            f", lookup={lookup}" if lookup is not None else "",
        )
        return Judgement(p, lookup, lookup_p, text=utterance)
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("turn judge timed out after %.2fs", timeout_s)
    except Exception as exc:
        logger.warning("turn judge failed: %s", exc)
    return Judgement(None, text=utterance)


def _lookup_answer(answer: object) -> tuple[str | None, float | None]:
    """(choice, its probability) from a choice answer, (None, None) if missing.
    Jev returns per-option probabilities; confidence stands in without them."""
    if not isinstance(answer, dict) or not isinstance(answer.get("choice"), str):
        return None, None
    choice = answer["choice"]
    probabilities = answer.get("probabilities") or {}
    p = probabilities.get(choice, answer.get("confidence"))
    if not isinstance(p, (int, float)):
        return choice, None
    return choice, min(1.0, max(0.0, float(p)))
