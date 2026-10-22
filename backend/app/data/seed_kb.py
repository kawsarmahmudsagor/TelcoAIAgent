"""Knowledge-base seed: the six telco policy/FAQ documents under app/data/kb/.
Each becomes a text RagSource with a pending ingest job; the scheduler embeds
them later, so seeding needs neither an embedding key nor Chroma. Never deletes."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.rag import RagSource
from app.repositories import agent_config_repo
from app.services import rag_service

KB_DIR = Path(__file__).parent / "kb"
NAME_PREFIX = "telco KB: "


def seed_kb(db: Session) -> int:
    """Create a source for every kb/*.md that has none yet and turn RAG on.
    Returns the number of sources created."""
    created = 0
    for path in sorted(KB_DIR.glob("*.md")):
        name = f"{NAME_PREFIX}{path.stem}"
        if db.scalar(select(RagSource.id).where(RagSource.name == name).limit(1)):
            continue
        rag_service.create_text_source(db, name=name, text=path.read_text(encoding="utf-8"))
        created += 1
    row = agent_config_repo.get_or_create(db)
    if not row.rag_enabled:
        agent_config_repo.update(db, row, {"rag_enabled": True})
    return created
