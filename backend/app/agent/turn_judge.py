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
    "A real estate agency's voice assistant is in a live call with a customer in Dhaka. "
    "The microphone also picks up other people in the room and background audio (TV, "
    "chatter). Decide whether the latest utterance is the customer speaking to the "
    "assistant about the real estate conversation, given the recent conversation. "
    "Customers speak English or Bangla; they address the assistant politely (আপনি), while "
    "family or friends in the room are addressed as তুমি/তুই. Short answers to the "
    "assistant's last question (a name, an email, a date, a number, yes/no) count. "
    "Requests on other topics (sports, news, weather, politics, general knowledge) do not "
    "count, even when asked to the assistant directly."
)

_CRITERIA = {
    "true": (
        "The customer is talking to the assistant about the real estate conversation: "
        "answering its question, asking about property, price, area, viewing, financing or "
        "the agency, correcting it, asking it to wait, stop or repeat, or a brief greeting, "
        "thanks or goodbye."
    ),
    "false": (
        "Someone talking to another person in the room, TV or radio audio, a request about "
        "an unrelated topic (sports, news, weather, politics, trivia), speech in a language "
        "other than English or Bangla, or garbled fragments that carry no request."
    ),
}


_LOOKUP_INSTRUCTIONS = (
    "Which lookup does the assistant need before it can answer the latest utterance? "
    "Pick a search only when the customer asks for properties or offers, or gives or "
    "changes what they want (area, budget, renting or buying, bedrooms, property type). "
    "Questions about listings already shown, booking a viewing, giving their name or "
    "phone, greetings and thanks need no lookup."
)

_LOOKUP_CRITERIA = {
    "listings": (
        "Search property listings: the customer asks what's available, or gives or changes "
        "search criteria (area, budget, rent or buy, bedrooms, property type)."
    ),
    "listings_with_offers": (
        "Search listings and the offers on them: the customer wants properties that have "
        "offers, discounts or deals."
    ),
    "offers": "Only offers or discounts, without a new property search.",
    "knowledge_base": (
        "A question about the agency, its policies, fees, process or the area in general, "
        "not about specific listings."
    ),
    "none": (
        "No lookup: a greeting, thanks, goodbye, a question about listings already shown, "
        "booking details, or anything else."
    ),
}


@dataclass(frozen=True)
class Judgement:
    """Jev's answers for one utterance. p = P(addressed), None when the call failed
    or timed out. lookup / lookup_p only when the lookup question was asked."""

    p: float | None
    lookup: str | None = None
    lookup_p: float | None = None


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
    search_context: str | None = None,
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
    if search_context:
        lines.append(search_context)
    return "\n".join(lines)


def search_context(last_search: dict | None, shown_listings: int) -> str:
    """What has been searched so far, so Jev can tell a follow-up on shown
    listings from a new search."""
    if not shown_listings and not last_search:
        return "No search has been run yet in this conversation."
    criteria = ", ".join(f"{k}={v}" for k, v in (last_search or {}).items()) or "no criteria"
    return f"Last search: {criteria}; {shown_listings} listings shown to the customer so far."


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
    search_context: str | None = None,
) -> dict:
    """lookup adds the router's choice question (knowledge_base: whether that's
    an option); search_context is a line about the search so far, so a follow-up
    on shown listings isn't taken for a new search."""
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
        "state": build_state(history, utterance, bot_state, address_form, search_context),
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
        return Judgement(p, lookup, lookup_p)
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("turn judge timed out after %.2fs", timeout_s)
    except Exception as exc:
        logger.warning("turn judge failed: %s", exc)
    return Judgement(None)


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
