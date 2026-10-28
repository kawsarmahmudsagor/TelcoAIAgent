"""The turn router's argument extractor: request shape, parsing and failure
handling. Requests go to an httpx.MockTransport, never the network."""

import asyncio
import json

import httpx
import pytest

from app.agent.turn_judge import Exchange
from word_checks import real_estate_words

from app.agent import turn_router
from app.agent.turn_router import RouterArgs, build_request, extract, parse

_BASE = "https://openrouter.ai/api/v1"

_FULL = {
    "packages": {"kind": "data", "max_price": 300, "min_data_gb": None, "validity_days": 7},
    "knowledge_query": None,
    "care_place": None,
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
    assert set(schema["properties"]) == {"packages", "knowledge_query", "care_place"}
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


# ---- fast rules ----


def _bench_cases():
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "router_bench" / "cases.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for case in data["cases"]:
        history = [Exchange(h["role"], h["text"]) for h in data["histories"][case["h"]]]
        yield pytest.param(case, history, id=case["id"])


@pytest.mark.parametrize("case, history", list(_bench_cases()))
def test_fast_rules_never_disagree_with_the_bench(case, history):
    """Either the extractor's exact arguments, or no answer at all."""
    args = turn_router.fast_extract(case["utterance"], history)
    if args is not None:
        assert case.get("packages") is not None and "allow_extra" not in case
        assert args.packages == case["packages"]


@pytest.mark.parametrize(
    "utterance, packages",
    [
        ("৩০০ টাকার মধ্যে ১০ জিবি ইন্টারনেট প্যাক কী কী আছে?", {"kind": "data", "max_price": 300, "min_data_gb": 10}),
        ("Show me weekly voice packs under 100 taka.", {"kind": "voice", "validity_days": 7, "max_price": 100}),
        ("500 takar moddhe 20 GB er data pack dekhao", {"kind": "data", "max_price": 500, "min_data_gb": 20}),
        ("sat diner jonno minute pack ache?", {"kind": "voice", "validity_days": 7}),
        ("10GB monthly data pack", {"kind": "data", "min_data_gb": 10, "validity_days": 30}),
        ("500 MB data pack under 50 taka", {"kind": "data", "min_data_gb": 0.5, "max_price": 50}),
        ("একটা কম্বো প্যাক দেখান", {"kind": "bundle"}),
        ("৩০ দিনের এসএমএস প্যাক", {"kind": "sms", "validity_days": 30}),
    ],
)
def test_fast_rules_read_a_plain_package_request(utterance, packages):
    args = turn_router.fast_extract(utterance, [])
    assert args is not None and args.packages == packages


@pytest.mark.parametrize(
    "utterance",
    [
        "৫০০ টাকা রিচার্জ করুন",  # a recharge, not a pack search
        "৩০০ টাকার প্যাক",  # a ceiling or a rough price?
        "ফেসবুক ছাড়া ডাটা প্যাক",  # a negation
        "১০ ডাটা প্যাক",  # a number with no unit
        "আমার ব্যালেন্স কত",
        "জিবি প্যাক",  # a unit with no number
    ],
)
def test_fast_rules_leave_anything_unclear_to_the_extractor(utterance):
    assert turn_router.fast_extract(utterance, []) is None


def test_fast_rules_step_aside_after_an_earlier_package_request():
    # The extractor carries the earlier criteria over; the rules can't.
    history = [Exchange("user", "১০ জিবি ডাটা প্যাক চাই"), Exchange("assistant", "...")]
    assert turn_router.fast_extract("সাপ্তাহিক মিনিট প্যাক", history) is None
    # An earlier message about something else changes nothing.
    history = [Exchange("user", "আমার ব্যালেন্স কত?"), Exchange("assistant", "...")]
    assert turn_router.fast_extract("সাপ্তাহিক মিনিট প্যাক", history) is not None
