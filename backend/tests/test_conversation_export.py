import io
import json
from datetime import datetime, timezone

import httpx
import pytest
from docx import Document
from docx.oxml.ns import qn

from app.config import get_settings
from app.services.conversation_export import (
    ExportHeader,
    ExportLine,
    ExportTranslationError,
    bangla_digits,
    needs_translation,
    render_docx,
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


# 2026-10-30 08:32 UTC is 14:32 in Dhaka.
_STARTED = datetime(2026, 10, 30, 8, 32, tzinfo=timezone.utc)


def _header(**overrides) -> ExportHeader:
    fields = dict(
        started_at=_STARTED,
        ended_at=_STARTED,
        channel="inbound_chat",
        is_phone_call=False,
        customer_name="Rahim Uddin",
        customer_msisdn="01712345678",
    )
    return ExportHeader(**(fields | overrides))


_LINES = [
    ExportLine(role="assistant", text="Hello! How can I help?", at=_STARTED),
    ExportLine(role="user", text="Call 01712345678 please", at=_STARTED),
]


def _text(data: bytes) -> str:
    return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)


def test_render_en_labels_and_title():
    text = _text(render_docx(_header(), _LINES, "en"))
    assert "telco chat transcript" in text
    assert "Assistant:" in text and "User:" in text
    assert "Hello! How can I help?" in text
    assert "14:32" in text and "Web chat" in text
    assert "telco." not in text


def test_render_bn_labels_and_digits():
    text = _text(render_docx(_header(), _LINES, "bn"))
    assert "telco চ্যাট ট্রান্সক্রিপ্ট" in text
    assert "সহকারী:" in text and "গ্রাহক:" in text
    assert "৩০ অক্টোবর ২০২৬" in text
    assert "Call 01712345678 please" in text
    assert "Assistant:" not in text


def test_render_header_customer():
    with_customer = _text(render_docx(_header(), _LINES, "en"))
    assert "Rahim Uddin" in with_customer and "01712345678" in with_customer
    guest = _text(render_docx(_header(customer_name=None, customer_msisdn=None), _LINES, "en"))
    assert "Customer" not in guest


def test_render_sets_cs_font():
    doc = Document(io.BytesIO(render_docx(_header(), _LINES, "bn")))
    runs = [run for p in doc.paragraphs for run in p.runs]
    assert runs
    for run in runs:
        assert run._element.rPr.rFonts.get(qn("w:cs")) == "Nirmala UI"


def test_bangla_digits():
    assert bangla_digits("2026-10-30 14:32") == "২০২৬-১০-৩০ ১৪:৩২"
