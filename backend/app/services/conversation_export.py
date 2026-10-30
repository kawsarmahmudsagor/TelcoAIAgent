"""Exports an ended conversation as a .docx in English or Bangla.

Messages not already in the export language are translated by an LLM through
OpenRouter, Banglish (Bangla in Latin letters) included. A translation that
fails in any way fails the whole export: never a half-translated file."""

import json
import re
from typing import Literal

import httpx

from app.config import Settings

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
