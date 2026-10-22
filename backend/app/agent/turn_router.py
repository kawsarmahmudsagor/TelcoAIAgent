"""Turn router: fills in a search's arguments so it can run before the LLM.

A search turn used to cost the LLM two round trips: one to pick the tool and its
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

_SYSTEM = """You fill in the arguments of a real estate agency's search tools from a \
voice conversation with a customer in Dhaka. The customer speaks Bangla, English or both. \
Fill both objects for the customer's latest message; the caller decides which one runs.

search -- arguments for searching property listings:
- Use only criteria the customer has stated or confirmed in this conversation: the \
latest message plus the earlier ones and the last search shown below, unless they've \
since changed it. Leave everything else null. Never invent a criterion, and never \
take one from what the assistant said (a listing it described is not something the \
customer asked for).
- location: the area or city in English spelling, whatever script they used \
(মোহাম্মদপুর -> "Mohammadpur", উত্তরা -> "Uttara", ধানমন্ডি -> "Dhanmondi"). Keep a \
sector or section number ("Mirpur 12", "Uttara Sector 7", মিরপুর ১২ -> "Mirpur 12") and \
drop words like "near", "kache" or "area". One area only: for two or more, use locations.
- locations / location_mode: two or more separate areas, each in English spelling, with \
location null. location_mode "all" when they want to see each ("A ebong B", "A and B", \
"A o B"), "any" when either will do ("A ba B", "A or B", "ei duitar moddhe", \
"je kono ekta"). An area with its city ("Uttara, Dhaka") is one location, not two.
- listing_type: "sale" for buying, "rent" for renting.
- budget_min / budget_max: plain numbers in taka. 1 lakh (লাখ) = 100000, \
1 crore (কোটি) = 10000000, 1 hajar (হাজার) = 1000. Rent budgets are monthly. When they \
switch between renting and buying, drop the old budget.
- budget_min_strict / budget_max_strict: true when the customer marks that bound as a \
hard limit with a word like minimum / at least / কমপক্ষে / er kom na (budget_min_strict) \
or maximum / max / at most / সর্বোচ্চ / er beshi na / er upore na (budget_max_strict). \
"maximum 15000" -> budget_max 15000, budget_max_strict true. "15000 er moddhe" alone -> \
false.
- property_type: apartment (a flat), studio, duplex, commercial (shop/office) or \
plot (land). বাসা, বাড়ি, বাড়ি ভাড়া, পুরো বাড়ি, ঘর, basa, bari, basha, "house" or \
"a home" all mean a flat: null. We have no separate houses. "villa" means duplex.
- bedrooms / bathrooms: the minimum they want.
- amenities: any of lift, generator_backup, parking, gas_line, gym, security_guard, \
rooftop_access, furnished that they asked for.
- more: true when they ask for more or other options with the same criteria \
("aro dekhao", "show me more", "আর কী আছে"), else false.

offers -- arguments for looking up offers and discounts:
- listing_number: the #number of a listing already shown, if they mean one.
- location: area in English spelling, if they named one.
- offer_type: percent_discount, flat_discount, single_payment_discount, \
installment_plan, reduced_booking_money, fee_waiver or free_parking, if they named a kind.

knowledge_query: the latest message as a short English search query about the \
agency, its process or fees, or null."""

_NULLABLE_STRING = {"type": ["string", "null"]}
_NULLABLE_NUMBER = {"type": ["number", "null"]}
_NULLABLE_INTEGER = {"type": ["integer", "null"]}

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["search", "offers", "knowledge_query"],
    "properties": {
        "search": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "location", "locations", "location_mode", "listing_type", "budget_min",
                "budget_max", "budget_min_strict", "budget_max_strict", "property_type",
                "bedrooms", "bathrooms", "amenities", "more",
            ],
            "properties": {
                "location": _NULLABLE_STRING,
                "locations": {"type": ["array", "null"], "items": {"type": "string"}},
                "location_mode": {"type": ["string", "null"], "enum": ["all", "any", None]},
                "listing_type": {"type": ["string", "null"], "enum": ["sale", "rent", None]},
                "budget_min": _NULLABLE_NUMBER,
                "budget_max": _NULLABLE_NUMBER,
                "budget_min_strict": {"type": "boolean"},
                "budget_max_strict": {"type": "boolean"},
                "property_type": _NULLABLE_STRING,
                "bedrooms": _NULLABLE_INTEGER,
                "bathrooms": _NULLABLE_NUMBER,
                "amenities": {"type": ["array", "null"], "items": {"type": "string"}},
                "more": {"type": "boolean"},
            },
        },
        "offers": {
            "type": "object",
            "additionalProperties": False,
            "required": ["listing_number", "location", "offer_type"],
            "properties": {
                "listing_number": _NULLABLE_INTEGER,
                "location": _NULLABLE_STRING,
                "offer_type": _NULLABLE_STRING,
            },
        },
        "knowledge_query": _NULLABLE_STRING,
    },
}  # fmt: skip


@dataclass(frozen=True)
class RouterArgs:
    """Arguments for each lookup, with unset (null) ones left out."""

    search: dict = field(default_factory=dict)
    offers: dict = field(default_factory=dict)
    knowledge_query: str | None = None


def build_request(
    model: str,
    history: list[Exchange],
    utterance: str,
    last_search: dict | None,
    shown_listings: int = 0,
    reasoning_effort: str = "none",
) -> dict:
    """reasoning_effort: an extraction needs none, and every reasoning token is
    latency; a model that can't turn reasoning off fails the request (the LLM
    then calls the tools itself)."""
    lines = ["Conversation so far:"]
    lines += [f"{'Customer' if e.role == 'user' else 'Assistant'}: {e.text}" for e in history]
    if not history:
        lines.append("(none yet)")
    if last_search:
        criteria = ", ".join(f"{k}={v}" for k, v in last_search.items())
        lines.append(f"Last search: {criteria}; {shown_listings} listings shown so far.")
    else:
        lines.append("No search has been run yet.")
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
        "max_tokens": 300,
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
        # A false flag is the default, left out like a null.
        search = {
            k: v
            for k, v in data["search"].items()
            if v is not False and v not in (None, [], "")
        }
        offers = {k: v for k, v in data["offers"].items() if v not in (None, "")}
        query = data.get("knowledge_query") or None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    if query is not None and not isinstance(query, str):
        return None
    return RouterArgs(search=search, offers=offers, knowledge_query=query)


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
