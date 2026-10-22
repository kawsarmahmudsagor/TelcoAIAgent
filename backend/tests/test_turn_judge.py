"""The Jev relevance judge: request shape and failure handling. Requests go to
an httpx.MockTransport, never the network."""

import asyncio
import json

import httpx
import pytest

from app.agent import turn_judge
from app.agent.turn_judge import Exchange, Judgement, build_request, decisions_url, judge

_URL = "https://openrouter.ai/api/alpha/decisions"


def _judgement(handler, timeout_s: float = 1.0, **request) -> Judgement:
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            payload = build_request("typesafe/jev-1.13", [], "hello", "listening", **request)
            return await judge(client, _URL, "or-key", payload, timeout_s)

    return asyncio.run(go())


def _judge(handler, timeout_s: float = 1.0) -> float | None:
    return _judgement(handler, timeout_s).p


@pytest.mark.parametrize(
    ("base", "expected"),
    [
        ("https://openrouter.ai/api/v1", _URL),
        ("https://openrouter.ai/api/v1/", _URL),
        ("https://proxy.example.com", "https://proxy.example.com/api/alpha/decisions"),
    ],
)
def test_decisions_url(base, expected):
    assert decisions_url(base) == expected


def test_request_is_one_noul_question_with_the_conversation_as_state():
    history = [
        Exchange("user", "বনানীতে ফ্ল্যাট লাগবে"),
        Exchange("assistant", "আপনার বাজেট কত?"),
    ]
    body = build_request("typesafe/jev-1.13", history, "৫০ লাখ", "speaking", "formal")
    assert body["model"] == "typesafe/jev-1.13"
    (key,) = body["questions"]
    assert key == turn_judge.QUESTION_KEY
    question = body["questions"][key]
    assert question["type"] == "noul"
    assert set(question["criteria"]) == {"true", "false"}
    state = body["state"]
    assert "Customer: বনানীতে ফ্ল্যাট লাগবে" in state
    assert "Assistant: আপনার বাজেট কত?" in state
    assert "'৫০ লাখ'" in state
    assert "speaking" in state
    assert "formal" in state


def test_request_without_history_or_address_form():
    state = build_request("m", [], "hi", "thinking")["state"]
    assert "(none yet)" in state
    assert "looking something up" in state
    assert "Form of address" not in state


def test_returns_the_probability():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"answers": {"addressed": {"type": "noul", "noul": 0.83}}}
        )

    assert _judge(handler) == pytest.approx(0.83)
    (request,) = seen
    assert str(request.url) == _URL
    assert request.headers["authorization"] == "Bearer or-key"
    assert json.loads(request.content)["questions"]["addressed"]["type"] == "noul"


def test_clamps_out_of_range_values():
    def handler(request):
        return httpx.Response(200, json={"answers": {"addressed": {"noul": 1.4}}})

    assert _judge(handler) == 1.0


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="upstream down"),
        httpx.Response(401, json={"error": "bad key"}),
        httpx.Response(200, json={"answers": {}}),
        httpx.Response(200, text="not json"),
    ],
)
def test_failures_return_none(response):
    assert _judge(lambda request: response) is None


def test_timeout_returns_none():
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={"answers": {"addressed": {"noul": 0.9}}})

    assert _judge(slow, timeout_s=0.05) is None


def test_lookup_question_is_added_only_when_asked():
    plain = build_request("m", [], "hi", "listening")
    assert set(plain["questions"]) == {turn_judge.QUESTION_KEY}

    routed = build_request(
        "m", [], "Uttara-te flat ache?", "listening", lookup=True, search_context="Last search: x"
    )
    question = routed["questions"][turn_judge.LOOKUP_KEY]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"listings", "listings_with_offers", "offers", "none"}
    assert "Last search: x" in routed["state"]

    with_kb = build_request("m", [], "hi", "listening", lookup=True, knowledge_base=True)
    assert "knowledge_base" in with_kb["questions"][turn_judge.LOOKUP_KEY]["criteria"]


def test_returns_the_lookup_choice_and_its_probability():
    def handler(request):
        return httpx.Response(200, json={"answers": {
            "addressed": {"type": "noul", "noul": 0.72},
            "lookup": {
                "type": "choice",
                "choice": "listings_with_offers",
                "probabilities": {"listings": 0.04, "listings_with_offers": 0.96},
                "confidence": 0.95,
            },
        }})  # fmt: skip

    assert _judgement(handler, lookup=True) == Judgement(0.72, "listings_with_offers", 0.96)


def test_lookup_falls_back_to_confidence_and_tolerates_a_bad_answer():
    def confidence_only(request):
        return httpx.Response(200, json={"answers": {
            "addressed": {"noul": 0.9}, "lookup": {"choice": "none", "confidence": 0.8},
        }})  # fmt: skip

    def garbled(request):
        return httpx.Response(200, json={"answers": {
            "addressed": {"noul": 0.9}, "lookup": {"oops": 1},
        }})  # fmt: skip

    assert _judgement(confidence_only, lookup=True) == Judgement(0.9, "none", 0.8)
    assert _judgement(garbled, lookup=True) == Judgement(0.9)


def test_failure_is_a_judgement_without_a_score():
    assert _judgement(lambda request: httpx.Response(500)) == Judgement(None)
