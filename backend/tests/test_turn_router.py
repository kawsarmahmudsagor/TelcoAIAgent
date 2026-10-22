"""The turn router's argument extractor: request shape, parsing and failure
handling. Requests go to an httpx.MockTransport, never the network."""

import asyncio
import json

import httpx
import pytest

from app.agent.turn_judge import Exchange
from app.agent.turn_router import RouterArgs, build_request, extract, parse

_BASE = "https://openrouter.ai/api/v1"

_FULL = {
    "search": {
        "location": "Uttara", "listing_type": "rent", "budget_min": None, "budget_max": 30000,
        "property_type": "apartment", "bedrooms": 3, "bathrooms": None, "amenities": [],
    },
    "offers": {"listing_number": None, "location": "Uttara", "offer_type": None},
    "knowledge_query": None,
}  # fmt: skip


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _extract(handler, timeout_s: float = 1.0) -> RouterArgs | None:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            payload = build_request("google/gemini-3.1-flash-lite", [], "hi", None)
            return await extract(client, _BASE, "or-key", payload, timeout_s)

    return asyncio.run(go())


def test_request_asks_for_strict_json_with_no_reasoning():
    history = [Exchange("assistant", "উত্তরায় ৪টি ফ্ল্যাট আছে।")]
    body = build_request(
        "m", history, "তিন বেডরুমের কিছু আছে?", {"location": "Uttara", "listing_type": "sale"}, 4
    )
    assert body["model"] == "m"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["reasoning"] == {"effort": "none"}
    assert body["provider"]["require_parameters"] is True
    assert body["provider"]["data_collection"] == "deny"
    assert "temperature" not in body
    user = body["messages"][1]["content"]
    assert "Assistant: উত্তরায় ৪টি ফ্ল্যাট আছে।" in user
    assert "Last search: location=Uttara, listing_type=sale; 4 listings shown" in user
    assert user.endswith("Customer's latest message: তিন বেডরুমের কিছু আছে?")


def test_request_without_a_search_yet():
    user = build_request("m", [], "hi", None)["messages"][1]["content"]
    assert "(none yet)" in user
    assert "No search has been run yet." in user


def test_parse_drops_unset_arguments():
    assert parse(json.dumps(_FULL)) == RouterArgs(
        search={
            "location": "Uttara", "listing_type": "rent", "budget_max": 30000,
            "property_type": "apartment", "bedrooms": 3,
        },
        offers={"location": "Uttara"},
    )  # fmt: skip


def test_parse_drops_false_flags_and_keeps_true_ones():
    content = {
        **_FULL,
        "search": {
            **_FULL["search"], "location": None, "locations": ["Dhanmondi", "Mirpur"],
            "location_mode": "any", "budget_min_strict": False, "budget_max_strict": True,
            "more": False,
        },
    }
    search = parse(json.dumps(content)).search
    assert search["budget_max_strict"] is True
    assert search["locations"] == ["Dhanmondi", "Mirpur"]
    assert "budget_min_strict" not in search and "more" not in search and "location" not in search


@pytest.mark.parametrize(
    "content", ["not json", "{}", json.dumps({"search": None, "offers": {}}), "[]"]
)
def test_parse_rejects_the_wrong_shape(content):
    assert parse(content) is None


def test_extract_returns_the_arguments():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _completion(json.dumps(_FULL))

    args = _extract(handler)
    assert args is not None and args.search["location"] == "Uttara"
    (request,) = seen
    assert str(request.url) == f"{_BASE}/chat/completions"
    assert request.headers["authorization"] == "Bearer or-key"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json={"error": "No endpoints found"}),
        httpx.Response(200, json={"choices": []}),
        _completion("not json"),
    ],
)
def test_failures_return_none(response):
    assert _extract(lambda request: response) is None


def test_timeout_returns_none():
    async def slow(request):
        await asyncio.sleep(1)
        return _completion(json.dumps(_FULL))

    assert _extract(slow, timeout_s=0.05) is None
