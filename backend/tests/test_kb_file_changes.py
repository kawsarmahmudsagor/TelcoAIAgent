"""A seeded KB doc edited on disk after seeding: the dashboard lists its source
as changed, and a reindex embeds the new text without deleting the source."""

import pytest
from sqlalchemy import text

from app.db.session import SessionLocal
from app.models.rag import RagSource
from app.services import kb_files, rag_service

STEM = "pytest-kb-file"
NAME = f"{kb_files.NAME_PREFIX}{STEM}"


@pytest.fixture
def kb_doc(tmp_path, monkeypatch):
    """A KB file in a temporary KB dir and its seeded text source."""
    monkeypatch.setattr(kb_files, "KB_DIR", tmp_path)
    path = tmp_path / f"{STEM}.md"
    path.write_text("# Fees\n\nThe fee is 50 taka.\n", encoding="utf-8")
    db = SessionLocal()
    try:
        source, _ = rag_service.create_text_source(
            db, name=NAME, text=path.read_text(encoding="utf-8")
        )
        source_id = source.id
    finally:
        db.close()
    yield path, source_id
    db = SessionLocal()
    try:
        db.execute(text("delete from rag_sources where name = :n"), {"n": NAME})
        db.commit()
    finally:
        db.close()


def _listed(api, source_id):
    items = api.get("/api/rag/sources", params={"limit": 500}).json()["items"]
    return next(item for item in items if item["id"] == str(source_id))


def test_an_unchanged_doc_is_not_flagged(api, kb_doc):
    _, source_id = kb_doc
    assert _listed(api, source_id)["file_changed"] is False


def test_an_edited_doc_is_flagged_and_counted(api, kb_doc):
    path, source_id = kb_doc
    before = api.get("/api/dashboard/rag-status").json()["kb_files_changed"]
    path.write_text("# Fees\n\nThe fee is 80 taka.\n", encoding="utf-8")
    assert _listed(api, source_id)["file_changed"] is True
    assert api.get("/api/dashboard/rag-status").json()["kb_files_changed"] == before + 1


def test_reindex_takes_the_new_text_and_clears_the_flag(api, kb_doc):
    path, source_id = kb_doc
    path.write_text("# Fees\n\nThe fee is 80 taka.\n", encoding="utf-8")
    response = api.post(f"/api/rag/sources/{source_id}/reindex")
    assert response.status_code == 202
    db = SessionLocal()
    try:
        source = db.get(RagSource, source_id)
        assert source.content == "# Fees\n\nThe fee is 80 taka."
        assert source.size_bytes == len(source.content.encode("utf-8"))
    finally:
        db.close()
    assert _listed(api, source_id)["file_changed"] is False


def test_a_deleted_file_or_a_plain_text_source_is_never_flagged(api, kb_doc):
    path, source_id = kb_doc
    path.unlink()
    assert _listed(api, source_id)["file_changed"] is False
    plain = RagSource(name="pytest note", source_type="text", content="x")
    assert kb_files.changed_text(plain) is None
