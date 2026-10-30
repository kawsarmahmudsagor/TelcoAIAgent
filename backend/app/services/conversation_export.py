"""Exports an ended conversation as a .docx in English or Bangla.

Messages not already in the export language are translated by an LLM through
OpenRouter, Banglish (Bangla in Latin letters) included. A translation that
fails in any way fails the whole export: never a half-translated file."""

import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.run import Run

from app.config import Settings, get_settings

ExportLang = Literal["en", "bn"]

CHUNK_SIZE = 40

_BENGALI = re.compile(r"[ঀ-৿]")
_LATIN = re.compile(r"[A-Za-z]")
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

_LANGUAGE_NAMES = {"en": "English", "bn": "Bangla (in Bengali script)"}

SYSTEM_PROMPT = """You translate a telecom customer-support chat for an exported transcript.
Target language: {language}.

You get a JSON array of {{"i": number, "text": string}}. Reply with only a JSON array of the
same objects, same "i" values, each "text" fully in the target language. No other text.

Rules:
- Translate every part that is not in the target language. Leave parts already in it unchanged.
- Banglish is Bangla written in Latin letters, and counts as Bangla: "amar balance koto?" is
  "আমার ব্যালেন্স কত?" in Bangla and "What is my balance?" in English.
- Bangla output: modern spoken Bangla, polite and natural, keeping common English loanwords
  (balance, recharge, SIM, internet). Not too casual.
- The brand is "telco": always lowercase, never with a dot after it.
- Always "package" in English and "প্যাকেজ" in Bangla, never "pack".
- Keep exactly as written: numbers, phone numbers, USSD codes such as *121#, URLs, amounts and
  currency, and package names.
"""


class ExportTranslationError(Exception):
    """The LLM call failed, timed out, or returned something unusable."""


def needs_translation(text: str, target: ExportLang) -> bool:
    """Whether `text` may hold anything not in `target`. Latin letters can be English or
    Banglish, so for an English export any letter at all goes to the LLM."""
    if target == "bn":
        return bool(_LATIN.search(text))
    return bool(_LATIN.search(text) or _BENGALI.search(text))


def translate(
    texts: list[str], target: ExportLang, *, client: httpx.Client, settings: Settings
) -> list[str]:
    """`texts` in `target`, same order; texts that need nothing are returned as they are."""
    out = list(texts)
    pending = [i for i, text in enumerate(texts) if needs_translation(text, target)]
    for start in range(0, len(pending), CHUNK_SIZE):
        chunk = pending[start : start + CHUNK_SIZE]
        translated = _translate_chunk({i: texts[i] for i in chunk}, target, client, settings)
        for i in chunk:
            out[i] = translated[i]
    return out


def _translate_chunk(
    items: dict[int, str], target: ExportLang, client: httpx.Client, settings: Settings
) -> dict[int, str]:
    payload = [{"i": i, "text": text} for i, text in items.items()]
    try:
        response = client.post(
            f"{settings.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": settings.export_translate_model,
                "temperature": 0,
                "reasoning": {"effort": "none"},
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT.format(language=_LANGUAGE_NAMES[target]),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise ExportTranslationError("translation request failed") from exc
    return _parse_reply(content, set(items))


def _parse_reply(content: str, expected: set[int]) -> dict[int, str]:
    if fenced := _FENCE.match(content):
        content = fenced.group(1)
    try:
        rows = json.loads(content)
        result = {int(row["i"]): str(row["text"]) for row in rows}
    except (ValueError, TypeError, KeyError) as exc:
        raise ExportTranslationError("translation reply is not the expected JSON") from exc
    if set(result) != expected or len(rows) != len(expected):
        raise ExportTranslationError("translation reply does not match the sent messages")
    return result


# --- .docx ---------------------------------------------------------------

CS_FONT = "Nirmala UI"
_ASSISTANT_COLOUR = RGBColor(0x1F, 0x6F, 0xEB)
_USER_COLOUR = RGBColor(0x2E, 0x7D, 0x32)
_GREY = RGBColor(0x6B, 0x72, 0x80)

_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
_BN_MONTHS = (
    "জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন",
    "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর",
)

_COPY = {
    "en": {
        "title": "telco chat transcript",
        "assistant": "Assistant:",
        "user": "User:",
        "started": "Started",
        "ended": "Ended",
        "channel": "Channel",
        "customer": "Customer",
        "number": "Number",
        "web": "Web chat",
        "phone": "Phone call",
    },
    "bn": {
        "title": "telco চ্যাট ট্রান্সক্রিপ্ট",
        "assistant": "সহকারী:",
        "user": "গ্রাহক:",
        "started": "শুরু",
        "ended": "শেষ",
        "channel": "মাধ্যম",
        "customer": "গ্রাহক",
        "number": "নম্বর",
        "web": "ওয়েব চ্যাট",
        "phone": "ফোন কল",
    },
}


@dataclass
class ExportLine:
    role: Literal["user", "assistant"]
    text: str
    at: datetime


@dataclass
class ExportHeader:
    started_at: datetime
    ended_at: datetime | None
    channel: str
    is_phone_call: bool
    customer_name: str | None
    customer_msisdn: str | None


def bangla_digits(s: str) -> str:
    return s.translate(_BN_DIGITS)


def _local(at: datetime) -> datetime:
    return at.astimezone(ZoneInfo(get_settings().agency_timezone))


def _date_time(at: datetime, lang: ExportLang) -> str:
    local = _local(at)
    if lang == "en":
        return local.strftime("%d %B %Y, %H:%M").lstrip("0")
    return bangla_digits(
        f"{local.day} {_BN_MONTHS[local.month - 1]} {local.year}, {local:%H:%M}"
    )


def _style(run: Run, *, bold: bool = False, size: float | None = None, colour=None) -> Run:
    """Every run names a complex-script font, so Word shapes Bangla correctly."""
    run.bold = bold
    if size is not None:
        run.font.size = Pt(size)
    if colour is not None:
        run.font.color.rgb = colour
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.get_or_add_rFonts()
    r_fonts.set(qn("w:cs"), CS_FONT)
    if _BENGALI.search(run.text):
        r_pr.get_or_add_cs()
    return run


def render_docx(header: ExportHeader, lines: list[ExportLine], lang: ExportLang) -> bytes:
    copy = _COPY[lang]
    doc = Document()
    title = doc.add_paragraph()
    _style(title.add_run(copy["title"]), bold=True, size=18)

    if header.is_phone_call:
        channel = copy["phone"]
    elif header.channel == "inbound_chat":
        channel = copy["web"]
    else:
        channel = header.channel
    fields = [(copy["started"], _date_time(header.started_at, lang))]
    if header.ended_at is not None:
        fields.append((copy["ended"], _date_time(header.ended_at, lang)))
    fields.append((copy["channel"], channel))
    if header.customer_name:
        fields.append((copy["customer"], header.customer_name))
    if header.customer_msisdn:
        fields.append((copy["number"], header.customer_msisdn))
    for label, value in fields:
        row = doc.add_paragraph()
        row.paragraph_format.space_after = Pt(0)
        _style(row.add_run(f"{label}: "), bold=True, size=10, colour=_GREY)
        _style(row.add_run(value), size=10, colour=_GREY)
    doc.add_paragraph()

    for line in lines:
        paragraph = doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        paragraph.paragraph_format.space_after = Pt(8)
        is_assistant = line.role == "assistant"
        _style(
            paragraph.add_run(copy["assistant"] if is_assistant else copy["user"]),
            bold=True,
            colour=_ASSISTANT_COLOUR if is_assistant else _USER_COLOUR,
        )
        time = f"{_local(line.at):%H:%M}"
        _style(
            paragraph.add_run(f"  {bangla_digits(time) if lang == 'bn' else time}"),
            size=9,
            colour=_GREY,
        )
        _style(paragraph.add_run()).add_break()
        _style(paragraph.add_run(line.text))

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
