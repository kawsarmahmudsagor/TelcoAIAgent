"""The turn router's argument extractor: request shape, parsing and failure
handling. Requests go to an httpx.MockTransport, never the network."""

import asyncio
import json

import httpx
import pytest

from app.agent.turn_judge import Exchange
from word_checks import real_estate_words

from app.agent.turn_router import RouterArgs, build_request, extract, parse

_BASE = "https://openrouter.ai/api/v1"

_FULL = {
    "packages": {"kind": "data", "max_price": 300, "min_data_gb": None, "validity_days": 7},
    "knowledge_query": None,
}


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def _extract(handler, timeout_s: float = 1.0) -> RouterArgs | None:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            payload = build_request("google/gemini-3.1-flash-lite", [], "hi")
            return await extract(client, _BASE, "or-key", payload, timeout_s)

    return asyncio.run(go())


def test_request_asks_for_strict_json_with_no_reasoning():
    history = [Exchange("assistant", "কত টাকার মধ্যে চান?")]
    body = build_request("m", history, "৩০০ টাকার ডাটা প্যাক আছে?")
    assert body["model"] == "m"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    schema = body["response_format"]["json_schema"]["schema"]
    assert set(schema["properties"]) == {"packages", "knowledge_query"}
    packages = schema["properties"]["packages"]["properties"]
    assert set(packages) == {"kind", "max_price", "min_data_gb", "validity_days"}
    assert packages["kind"]["enum"] == ["data", "voice", "bundle", "sms", None]
    assert body["reasoning"] == {"effort": "none"}
    assert body["provider"]["require_parameters"] is True
    assert body["provider"]["data_collection"] == "deny"
    assert "temperature" not in body
    user = body["messages"][1]["content"]
    assert "Assistant: কত টাকার মধ্যে চান?" in user
    assert user.endswith("Customer's latest message: ৩০০ টাকার ডাটা প্যাক আছে?")
    assert not real_estate_words(body["messages"][0]["content"])


def test_request_without_history():
    user = build_request("m", [], "hi")["messages"][1]["content"]
    assert "(none yet)" in user


def test_parse_drops_unset_arguments():
    assert parse(json.dumps(_FULL)) == RouterArgs(
        packages={"kind": "data", "max_price": 300, "validity_days": 7}
    )


def test_parse_keeps_the_knowledge_query():
    content = {"packages": {"kind": None}, "knowledge_query": "roaming charges"}
    assert parse(json.dumps(content)) == RouterArgs(knowledge_query="roaming charges")


@pytest.mark.parametrize(
    "content", ["not json", "{}", json.dumps({"packages": None}), "[]"]
)
def test_parse_rejects_the_wrong_shape(content):
    assert parse(content) is None


def test_extract_returns_the_arguments():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _completion(json.dumps(_FULL))

    args = _extract(handler)
    assert args is not None and args.packages["kind"] == "data"
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
