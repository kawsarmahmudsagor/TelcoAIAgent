"""Compare translation models for the conversation export
(app.services.conversation_export.translate).

Translates sample chat lines (Banglish, mixed, English, Bangla) plus the
messages of the most recent ended conversations into both export languages
with each model, and writes a Markdown report with the outputs side by side
and each model's time, for a person to judge.

Run from backend/ so the backend environment and .env are used:
    cd backend && uv run python ../scripts/export_translate_bench/run.py \
        --models google/gemini-3.5-flash openai/gpt-6-luna google/gemini-3.5-flash-lite
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.conversation import Conversation  # noqa: E402
from app.repositories import conversation_repo  # noqa: E402
from app.services.conversation_export import ExportTranslationError, translate  # noqa: E402

DEFAULT_MODELS = [
    "google/gemini-3.5-flash",
    "openai/gpt-6-luna",
    "google/gemini-3.5-flash-lite",
]

SAMPLES = [
    "amar balance koto?",
    "ami ekta 10 GB internet package nite chai, koto taka lagbe?",
    "amar net onek slow keno? *121# dial korlam kintu kaj hocche na",
    "আমার balance কত? আর আমার package কবে শেষ হবে?",
    "I want to recharge 500 taka to 01712345678.",
    "Your 30-day 20 GB package costs 499 taka. Shall I activate it?",
    "আপনার বর্তমান ব্যালেন্স ১২০ টাকা। আর কিছু জানতে চান?",
    "SIM replacement er jonno kothay jete hobe? Banani te kono care centre ache?",
]


def _recent_messages(limit: int) -> list[str]:
    db = SessionLocal()
    try:
        conversations = (
            db.query(Conversation)
            .filter(Conversation.status == "ended", Conversation.message_count > 2)
            .order_by(Conversation.started_at.desc())
            .limit(limit)
            .all()
        )
        return [
            m.text
            for c in conversations
            for m in conversation_repo.list_visible_messages(db, c.id)
            if m.text and m.text.strip()
        ]
    finally:
        db.close()


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--conversations", type=int, default=6)
    parser.add_argument("--out", type=Path, default=_HERE / "report.md")
    args = parser.parse_args()

    texts = SAMPLES + _recent_messages(args.conversations)
    settings = get_settings()
    lines = [f"# Export translation bench ({len(texts)} lines)", ""]
    with httpx.Client(timeout=settings.export_translate_timeout_s) as client:
        for target in ("bn", "en"):
            results: dict[str, list[str]] = {}
            timings: dict[str, str] = {}
            for model in args.models:
                tuned = settings.model_copy(update={"export_translate_model": model})
                started = time.perf_counter()
                try:
                    results[model] = translate(texts, target, client=client, settings=tuned)
                    timings[model] = f"{time.perf_counter() - started:.1f} s"
                except ExportTranslationError as exc:
                    results[model] = ["(failed)"] * len(texts)
                    timings[model] = f"failed: {exc.__cause__ or exc}"
                print(f"{target} {model}: {timings[model]}")
            lines += [f"## Into {'Bangla' if target == 'bn' else 'English'}", ""]
            lines += [f"- {model}: {timings[model]}" for model in args.models] + [""]
            lines.append("| original | " + " | ".join(args.models) + " |")
            lines.append("|---" * (len(args.models) + 1) + "|")
            for i, text in enumerate(texts):
                row = [_cell(text)] + [_cell(results[m][i]) for m in args.models]
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
