"""Turn router: fills in a lookup's arguments so it can run before the LLM.

A lookup turn used to cost the LLM two round trips: one to pick the tool and its
arguments, one to answer from the result. Jev already judges every finished
turn and, with the router on, says which lookup it needs (turn_judge.LOOKUP_KEY).
Jev can only answer typed questions, not write arguments, so this small, fast
LLM call -- started alongside Jev -- extracts them as JSON. The gate then runs
the search and hands the result to the LLM as if it had called the tool itself,
leaving it one round trip.

Kept free of livekit imports so scripts/router_bench can drive the exact request
the agent sends.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.agent.turn_judge import Exchange

logger = logging.getLogger(__name__)
# Same logger as app.agent.usage_log, so all provider usage lines filter together.
usage_logger = logging.getLogger("agent.usage")

_SYSTEM = """You fill in the arguments of a mobile operator's package search from a \
conversation with a customer in Bangladesh. The customer speaks Bangla, English or both. \
Fill both fields for the customer's latest message; the caller decides which one runs.

packages -- arguments for searching the operator's packages:
- Use only criteria the customer has stated or confirmed in this conversation: the \
latest message plus the earlier ones, unless they've since changed it. Leave everything \
else null. Never invent a criterion, and never take one from what the assistant said (a \
pack it described is not something the customer asked for).
- kind: "data" for internet / data / ডাটা / নেট packs, "voice" for minutes / talk-time / \
মিনিট packs, "bundle" for combo packs with data and minutes together, "sms" for SMS packs.
- max_price: plain number in taka, the most they want to pay ("৩০০ টাকার মধ্যে" -> 300, \
"under 500" -> 500, "এক হাজার" -> 1000).
- min_data_gb: the least data they want, in GB as a number ("10 GB" -> 10, "৫০০ এমবি" -> 0.5).
- validity_days: how long the pack should last in days ("7 din" -> 7, "এক মাস" -> 30, \
"সাপ্তাহিক" -> 7).

knowledge_query: the latest message as a short English search query about the operator's \
services, policies, coverage or how something works, or null."""

_NULLABLE_STRING = {"type": ["string", "null"]}
_NULLABLE_NUMBER = {"type": ["number", "null"]}
_NULLABLE_INTEGER = {"type": ["integer", "null"]}

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["packages", "knowledge_query"],
    "properties": {
        "packages": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "max_price", "min_data_gb", "validity_days"],
            "properties": {
                "kind": {
                    "type": ["string", "null"],
                    "enum": ["data", "voice", "bundle", "sms", None],
                },
                "max_price": _NULLABLE_NUMBER,
                "min_data_gb": _NULLABLE_NUMBER,
                "validity_days": _NULLABLE_INTEGER,
            },
        },
        "knowledge_query": _NULLABLE_STRING,
    },
}


@dataclass(frozen=True)
class RouterArgs:
    """Arguments for each lookup, with unset (null) ones left out."""

    packages: dict = field(default_factory=dict)
    knowledge_query: str | None = None


def build_request(
    model: str,
    history: list[Exchange],
    utterance: str,
    reasoning_effort: str = "none",
) -> dict:
    """reasoning_effort: an extraction needs none, and every reasoning token is
    latency; a model that can't turn reasoning off fails the request (the LLM
    then calls the tools itself)."""
    lines = ["Conversation so far:"]
    lines += [f"{'Customer' if e.role == 'user' else 'Assistant'}: {e.text}" for e in history]
    if not history:
        lines.append("(none yet)")
    lines.append(f"Customer's latest message: {utterance}")
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "\n".join(lines)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "lookup_arguments", "strict": True, "schema": _SCHEMA},
        },
        # No temperature: OpenAI's reasoning models reject it, and with
        # require_parameters that leaves no endpoint at all.
        "max_tokens": 200,
        "reasoning": {"effort": reasoning_effort},
        # require_parameters: never routed to a provider that would ignore
        # response_format; sort: the fastest one. Customer speech: keep it out of
        # provider training data.
        "provider": {
            "require_parameters": True,
            "sort": "latency",
            "data_collection": "deny",
        },
    }


def parse(content: str) -> RouterArgs | None:
    """The model's JSON, with nulls dropped; None if it isn't the expected shape."""
    try:
        data = json.loads(content)
        packages = {k: v for k, v in data["packages"].items() if v not in (None, "")}
        query = data.get("knowledge_query") or None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if query is not None and not isinstance(query, str):
        return None
    return RouterArgs(packages=packages, knowledge_query=query)


async def extract(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    payload: dict,
    timeout_s: float,
) -> RouterArgs | None:
    """The lookup arguments for the turn, or None on any error or timeout (the
    LLM then calls the tools itself, as without the router)."""
    started = time.perf_counter()
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
            "Router %s: %s input tokens, %s output, $%s, %dms",
            body.get("model") or payload.get("model"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
            f"{cost:.6f}" if isinstance(cost, (int, float)) else "?",
            (time.perf_counter() - started) * 1000,
        )
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("turn router timed out after %.2fs", timeout_s)
        return None
    except Exception as exc:
        logger.warning("turn router failed: %s", exc)
        return None
    args = parse(content) if isinstance(content, str) else None
    if args is None:
        logger.warning("turn router returned unusable arguments: %r", content)
    return args
