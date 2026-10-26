"""The knowledge-base files shipped in app/data/kb/ and the text sources seeded
from them (app.data.seed_kb). A source is linked to its file by name,
"telco KB: <file stem>", so a file edited after seeding shows up on the
dashboard as changed, and a reindex embeds the new text in place
(rag_service.reindex_source) instead of the source being deleted and re-added."""

from pathlib import Path

from app.models.rag import RagSource, RagSourceType

KB_DIR = Path(__file__).resolve().parents[1] / "data" / "kb"
NAME_PREFIX = "telco KB: "


def file_for(source: RagSource) -> Path | None:
    """The KB file a seeded text source came from, if it is still there."""
    if source.source_type != RagSourceType.text.value or not source.name.startswith(NAME_PREFIX):
        return None
    path = KB_DIR / f"{source.name[len(NAME_PREFIX):]}.md"
    return path if path.is_file() else None


def changed_text(source: RagSource) -> str | None:
    """The file's text when it differs from what the source holds, else None.
    Compared the way create_text_source stores it (stripped)."""
    path = file_for(source)
    if path is None:
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text if text and text != (source.content or "") else None
