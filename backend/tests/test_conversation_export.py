import json

import httpx
import pytest

from app.config import get_settings
from app.services.conversation_export import (
    ExportTranslationError,
    needs_translation,
    translate,
)


@pytest.mark.parametrize(
    "text,target,expected",
    [
        ("What is my balance?", "bn", True),
        ("amar balance koto", "bn", True),
        ("আমার ব্যালেন্স কত?", "bn", False),
        ("আমার balance কত?", "bn", True),
        ("*121# 500", "bn", False),
        ("What is my balance?", "en", True),
        ("amar balance koto", "en", True),
        ("আমার ব্যালেন্স কত?", "en", True),
        ("*121# 500", "en", False),
    ],
)
def test_needs_translation(text, target, expected):
    assert needs_translation(text, target) is expected


def _llm(handler):
    """An httpx client whose OpenRouter calls go to `handler(items) -> reply content`."""
    requests: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        items = json.loads(body["messages"][-1]["content"])
        content = handler(items)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return httpx.Client(transport=httpx.MockTransport(respond)), requests


def _echo_upper(items):
    return json.dumps([{"i": item["i"], "text": item["text"].upper()} for item in items])


def test_translate_sends_only_needed_texts():
    client, requests = _llm(_echo_upper)
    texts = ["hello", "আমার ব্যালেন্স কত?", "*121#", "amar net slow"]
    out = translate(texts, "bn", client=client, settings=get_settings())
    assert out == ["HELLO", "আমার ব্যালেন্স কত?", "*121#", "AMAR NET SLOW"]
    sent = [item["text"] for item in json.loads(requests[0]["messages"][-1]["content"])]
    assert sent == ["hello", "amar net slow"]


def test_translate_banglish_both_ways():
    for target in ("bn", "en"):
        client, requests = _llm(_echo_upper)
        translate(["amar net slow keno"], target, client=client, settings=get_settings())
        sent = json.loads(requests[0]["messages"][-1]["content"])
        assert [item["text"] for item in sent] == ["amar net slow keno"]


def test_translate_nothing_needed_makes_no_call():
    client, requests = _llm(_echo_upper)
    assert translate(["আমি ভালো আছি"], "bn", client=client, settings=get_settings()) == [
        "আমি ভালো আছি"
    ]
    assert requests == []


def test_translate_chunks_above_40():
    client, requests = _llm(_echo_upper)
    out = translate([f"line {n}" for n in range(41)], "bn", client=client, settings=get_settings())
    assert len(requests) == 2
    assert out[40] == "LINE 40"


def test_translate_accepts_fenced_json():
    client, _ = _llm(lambda items: "```json\n" + _echo_upper(items) + "\n```")
    assert translate(["hi"], "bn", client=client, settings=get_settings()) == ["HI"]


def test_translate_missing_index_fails():
    client, _ = _llm(lambda items: json.dumps([{"i": items[0]["i"], "text": "x"}]))
    with pytest.raises(ExportTranslationError):
        translate(["one", "two"], "bn", client=client, settings=get_settings())


def test_translate_bad_json_fails():
    client, _ = _llm(lambda items: "not json")
    with pytest.raises(ExportTranslationError):
        translate(["one"], "bn", client=client, settings=get_settings())


def test_translate_http_error_fails():
    server_error = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(ExportTranslationError):
        translate(["one"], "bn", client=server_error, settings=get_settings())

    def time_out(request):
        raise httpx.ReadTimeout("slow", request=request)

    timeout = httpx.Client(transport=httpx.MockTransport(time_out))
    with pytest.raises(ExportTranslationError):
        translate(["one"], "bn", client=timeout, settings=get_settings())


def test_translate_prompt_rules():
    client, requests = _llm(_echo_upper)
    translate(["hi"], "bn", client=client, settings=get_settings())
    body = requests[0]
    system = body["messages"][0]["content"]
    for rule in ("Banglish", "telco", "প্যাকেজ", "*121#"):
        assert rule in system
    assert body["model"] == get_settings().export_translate_model == "google/gemini-3.5-flash"
