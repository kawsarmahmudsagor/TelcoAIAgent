"""The Jev relevance judge: request shape and failure handling. Requests go to
an httpx.MockTransport, never the network."""

import asyncio
import inspect
import json

import httpx
import pytest
from word_checks import real_estate_words

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
        Exchange("user", "ডাটা প্যাক লাগবে"),
        Exchange("assistant", "কত টাকার মধ্যে?"),
    ]
    body = build_request("typesafe/jev-1.13", history, "তিনশো টাকা", "speaking", "formal")
    assert body["model"] == "typesafe/jev-1.13"
    (key,) = body["questions"]
    assert key == turn_judge.QUESTION_KEY
    question = body["questions"][key]
    assert question["type"] == "noul"
    assert set(question["criteria"]) == {"true", "false"}
    state = body["state"]
    assert "Customer: ডাটা প্যাক লাগবে" in state
    assert "Assistant: কত টাকার মধ্যে?" in state
    assert "'তিনশো টাকা'" in state
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

    routed = build_request("m", [], "৩০০ টাকার প্যাক আছে?", "listening", lookup=True)
    question = routed["questions"][turn_judge.LOOKUP_KEY]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"packages", "care_centre", "none"}  # knowledge_base only with RAG
    assert "search" not in routed["state"].lower()

    with_kb = build_request("m", [], "hi", "listening", lookup=True, knowledge_base=True)
    criteria = with_kb["questions"][turn_judge.LOOKUP_KEY]["criteria"]
    assert set(criteria) == {"packages", "care_centre", "knowledge_base", "none"}


def test_request_takes_no_search_context():
    assert "search_context" not in inspect.signature(build_request).parameters
    assert not hasattr(turn_judge, "search_context")


def test_prompts_have_no_real_estate_words():
    body = build_request("m", [], "hi", "listening", lookup=True, knowledge_base=True)
    text = json.dumps(body["questions"], ensure_ascii=False)
    assert not real_estate_words(text)


def test_returns_the_lookup_choice_and_its_probability():
    def handler(request):
        return httpx.Response(200, json={"answers": {
            "addressed": {"type": "noul", "noul": 0.72},
            "lookup": {
                "type": "choice",
                "choice": "packages",
                "probabilities": {"packages": 0.96, "none": 0.04},
                "confidence": 0.95,
            },
        }})  # fmt: skip

    assert _judgement(handler, lookup=True) == Judgement(0.72, "packages", 0.96)


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


def test_over_the_agent_jev_hears_what_it_is_saying():
    # run_27: "দুই জিবিরটা দেখান" over a list of packages, with the list not yet
    # in the history, scored 0.12 and was dropped.
    from types import SimpleNamespace

    from app.agent import gated_agent

    sent: list[dict] = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(500)

    session = SimpleNamespace(history=SimpleNamespace(items=[]))
    settings = SimpleNamespace(
        openrouter_base_url="https://openrouter.ai/api/v1",
        turn_judge_model="typesafe/jev-1.13",
        turn_judge_timeout_ms=1000,
    )
    listing = "আমাদের কাছে ১ জিবি ২৯ টাকা, ২ জিবি ৪৯ টাকা"

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            judge_fn = gated_agent.jev_judge(session, settings, "or-key", client)
            await judge_fn("দুই জিবিরটা দেখান", "speaking", speaking=listing)
            await judge_fn("দুই জিবিরটা দেখান", "listening")

    asyncio.run(go())
    assert f"Assistant: {listing} …" in sent[0]["state"]
    assert "Assistant:" not in sent[1]["state"]
