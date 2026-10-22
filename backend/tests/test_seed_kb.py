"""The KB seed documents. The fixture removes prior `telco KB:` sources the way
the app does (rag_service.delete_source: vectors, files, rows and their jobs)
so a clean run is observable; seed_kb commits, so the dev DB is left with the
six sources afterwards."""

import re

import pytest
from sqlalchemy import select

from app.data import seed_kb, seed_telco
from app.models.rag import EmbeddingJob, RagSource
from app.repositories import agent_config_repo
from app.services import rag_service

PREFIX = "telco KB: "


@pytest.fixture
def clean_kb(db):
    for source in _kb_sources(db):
        rag_service.delete_source(db, source.id)
    yield db


def _kb_sources(db):
    return db.scalars(select(RagSource).where(RagSource.name.like(f"{PREFIX}%"))).all()


def test_seed_kb_creates_sources_and_pending_jobs_once(clean_kb):
    db = clean_kb
    assert seed_kb.seed_kb(db) == 6
    sources = _kb_sources(db)
    assert len(sources) == 6
    jobs = db.scalars(
        select(EmbeddingJob).where(EmbeddingJob.rag_source_id.in_([s.id for s in sources]))
    ).all()
    assert len(jobs) == 6 and {j.status for j in jobs} == {"pending"}
    assert agent_config_repo.get(db).rag_enabled is True
    assert seed_kb.seed_kb(db) == 0
    assert len(_kb_sources(db)) == 6


def test_every_doc_is_bilingual():
    docs = sorted(seed_kb.KB_DIR.glob("*.md"))
    assert len(docs) == 6
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        assert re.search(r"[\u0980-\u09FF]", text), doc.name
        assert re.search(r"[A-Za-z]", text), doc.name


def test_package_terms_cover_every_active_package():
    text = (seed_kb.KB_DIR / "package-terms.md").read_text(encoding="utf-8")
    for code, *_ in seed_telco.PACKAGES:
        assert code in text, code
