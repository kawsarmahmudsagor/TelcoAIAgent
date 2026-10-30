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
# Whether the customer is closing the topic, so the reply offers more help
# (app.agent.closing_offer), asked in the same request.
WRAP_UP_KEY = "wrap_up"
# What the turn is about, for the filler line (app.agent.quick_reply), asked
# with the lookup question when quick fillers are on.
TOPIC_KEY = "topic"
# What the customer wants done, for the guest route (app.agent.quick_reply),
# asked with the topic question.
INTENT_KEY = "intent"

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
    "care_centre": (
        "The customer asks where a care centre, customer care, office, branch or store is, "
        "or which one is nearest to them or to a place."
    ),
    "knowledge_base": (
        "A question about the operator, its policies, coverage, fees or how a service "
        "works, not about the customer's own account or where a care centre is."
    ),
    "none": (
        "No lookup: a question about the customer's own account (balance, usage, current "
        "pack, offers), a purchase, recharge, redeem or complaint request, a code being "
        "read out, a greeting, thanks, goodbye, or anything else."
    ),
}


_WRAP_UP_INSTRUCTIONS = (
    "Is the customer closing the current topic with this utterance, rather than asking about "
    "it or continuing it? A person on a helpline would then ask whether they need anything "
    "else."
)

_WRAP_UP_CRITERIA = {
    "true": (
        "The customer accepts or acknowledges the answer (ok, ঠিক আছে, আচ্ছা, বুঝেছি, বুঝলাম, got "
        "it), thanks the assistant, says what they'll do now (তাহলে ওটাই করব, I'll go there), "
        "or declines what was offered without asking anything new (না, লাগবে না)."
    ),
    "false": (
        "The customer asks a question, a follow-up or for more detail, makes a request, gives "
        "information the assistant asked for (a number, a code, a choice, yes to an offer), "
        "corrects the assistant, or says goodbye outright."
    ),
}


_TOPIC_INSTRUCTIONS = (
    "What is the latest utterance asking about? Pick the customer's request in this "
    "utterance, read with the recent conversation (a short follow-up such as 'চার জিবির?' "
    "after data packages is still about data packages). When it asks two things, pick the "
    "main one."
)

# The names are quick_reply's filler topics (_TOPIC_X), so a choice picks its lines.
_TOPIC_CRITERIA = {
    "balance": "The customer's main account balance (ব্যালেন্স).",
    "usage": (
        "How much of their own data, minutes or SMS is used or left, or what they spent "
        "lately, not packages to buy."
    ),
    "data": "Data or internet packages to buy, by amount, price or validity.",
    "voice": "Minute or talk-time packages to buy.",
    "bundle": "Combo or bundle packages (data and minutes together) to buy.",
    "sms": "SMS packages to buy.",
    "pack": (
        "Packages to buy of no named kind, or one package already shown or named, "
        "without saying data, minutes, combo or SMS."
    ),
    "offer": "Offers or deals on their number.",
    "points": "Reward points: how many, earning them or redeeming them.",
    "transactions": "Money or balance deducted, a charge they don't recognise, recent transactions.",
    "recharge": (
        "Recharging or top-up: a recharge that didn't arrive, how to recharge, limits, or "
        "recharge bonuses."
    ),
    "network": "Network, signal, slow internet or dropped calls where they are.",
    "care": "Where a care centre, customer care office, branch or store is.",
    "complaint": "A complaint or a problem with the service not covered above.",
    "policy": "How a service, rule, fee or policy of the operator works.",
    "other": (
        "None of these: a greeting, thanks, goodbye, a code or yes/no, a purchase "
        "confirmation, or anything else."
    ),
}


_INTENT_INSTRUCTIONS = (
    "What does the customer want the assistant to do with the latest utterance? Read it "
    "with the recent conversation: a short yes right after the assistant offered to "
    "activate a package is a request to activate it, and a yes after it offered more "
    "packages is a request to hear them. When the utterance asks two things, pick the main one."
)

# Scored on 85 past turns (2026-10-30): 95%, against 91% for the word rules it
# replaces, and every miss below p 0.72.
_INTENT_CRITERIA = {
    "buy_named": (
        "Buy or activate one specific package already shown, named or offered in the "
        "conversation (ওটা নিব, দ্বিতীয়টা নিব, packageটা চালু করে দিন, yes to চালু করে দেবো?). "
        "Not when they still describe what they want or ask what is available."
    ),
    "search": (
        "Find or hear about packages to buy: what packages exist, more options, details or "
        "the price of one, or packages by data, minutes, price, validity or use, even when "
        "they say they want to buy."
    ),
    "recharge_do": "Recharge or top up their number now, not asking how recharging works.",
    "own_account": (
        "Their own account: balance, data or minutes left, current package, spending, "
        "charges or deductions, transactions, a recharge that didn't arrive, reward points, "
        "offers on their number, their complaints or cases, their registration, or a "
        "package suggestion based on their own usage."
    ),
    "person": "To talk to a human, a real person, an agent or a supervisor.",
    "how_to": (
        "How a service, process, rule or fee works, or where to go: a new SIM, SIM "
        "replacement, porting, postpaid, roaming, closing a SIM, how to recharge or buy, "
        "auto renewal, care centres."
    ),
    "other": (
        "Anything else: a greeting, thanks, ok, declining an offer, a code or number read "
        "out, network or signal problems, small talk, or asking what was said earlier."
    ),
}


@dataclass(frozen=True)
class Judgement:
    """Jev's answers for one utterance. p = P(addressed), None when the call failed
    or timed out. lookup / lookup_p only when the lookup question was asked, and
    topic / topic_p only when the topic question was, intent / intent_p only
    when the intent question was. wrap_up_p: P(the customer is closing the
    topic), None when not answered."""

    p: float | None
    lookup: str | None = None
    lookup_p: float | None = None
    text: str | None = None
    wrap_up_p: float | None = None
    topic: str | None = None
    topic_p: float | None = None
    intent: str | None = None
    intent_p: float | None = None


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
    wrap_up: bool = True,
    topic: bool = False,
    intent: bool = False,
) -> dict:
    """lookup adds the router's choice question (knowledge_base: whether that's
    an option); wrap_up the closing-the-topic question; topic the filler's
    what-is-it-about question; intent the guest route's what-to-do question."""
    questions: dict = {
        QUESTION_KEY: {
            "type": "noul",
            "instructions": _INSTRUCTIONS,
            "criteria": _CRITERIA,
        }
    }
    if lookup:
        questions[LOOKUP_KEY] = lookup_question(knowledge_base)
    if wrap_up:
        questions[WRAP_UP_KEY] = {
            "type": "noul",
            "instructions": _WRAP_UP_INSTRUCTIONS,
            "criteria": _WRAP_UP_CRITERIA,
        }
    if topic:
        questions[TOPIC_KEY] = {
            "type": "choice",
            "instructions": _TOPIC_INSTRUCTIONS,
            "criteria": _TOPIC_CRITERIA,
        }
    if intent:
        questions[INTENT_KEY] = {
            "type": "choice",
            "instructions": _INTENT_INSTRUCTIONS,
            "criteria": _INTENT_CRITERIA,
        }
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
        topic, topic_p = _lookup_answer(answers.get(TOPIC_KEY))
        intent, intent_p = _lookup_answer(answers.get(INTENT_KEY))
        if intent not in _INTENT_CRITERIA:
            intent, intent_p = None, None
        wrap_up_p = _noul(answers.get(WRAP_UP_KEY))
        usage = body.get("usage") or {}
        cost = usage.get("cost")
        usage_logger.info(
            "Jev %s: %s input tokens, $%s, %dms, P=%.2f%s%s%s",
            body.get("model") or payload.get("model"),
            usage.get("input_tokens", "?"),
            f"{cost:.6f}" if isinstance(cost, (int, float)) else "?",
            (time.perf_counter() - started) * 1000,
            p,
            f", lookup={lookup}" if lookup is not None else "",
            f", topic={topic}" if topic is not None else "",
            f", intent={intent}" if intent is not None else "",
        )
        return Judgement(
            p,
            lookup,
            lookup_p,
            text=utterance,
            wrap_up_p=wrap_up_p,
            topic=topic,
            topic_p=topic_p,
            intent=intent,
            intent_p=intent_p,
        )
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("turn judge timed out after %.2fs", timeout_s)
    except Exception as exc:
        logger.warning("turn judge failed: %s", exc)
    return Judgement(None, text=utterance)


def _noul(answer: object) -> float | None:
    """A yes/no answer's probability, None if missing."""
    if not isinstance(answer, dict) or not isinstance(answer.get("noul"), (int, float)):
        return None
    return min(1.0, max(0.0, float(answer["noul"])))


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
