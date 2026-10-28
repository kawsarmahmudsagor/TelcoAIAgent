"""The KB seed documents. The fixture removes prior `telco KB:` sources the way
the app does (rag_service.delete_source: vectors, files, rows and their jobs)
so a clean run is observable; seed_kb commits, so the dev DB is left with the
twelve sources afterwards."""

import re

import pytest
from sqlalchemy import select

from word_checks import real_estate_words

from app.data import seed_kb, seed_telco
from app.models.rag import EmbeddingJob, RagSource
from app.repositories import agent_config_repo
from app.services import kb_files, rag_service

PREFIX = "telco KB: "
DOC_COUNT = 13

# The KB was written from a real operator's public pages; the bot must only ever
# speak as telco, so none of its names, products, numbers or addresses may stay.
OTHER_BRANDS = re.compile(
    r"banglalink|mybl|toffee|veon|ryze|tigers?'? den|monobrand|desh ek rate"
    r"|grameenphone|robi|airtel|teletalk|1911304121|01950\s?111|\*121\*",
    re.IGNORECASE,
)


@pytest.fixture
def clean_kb(db):
    for source in _kb_sources(db):
        rag_service.delete_source(db, source.id)
    yield db


def _kb_sources(db):
    return db.scalars(select(RagSource).where(RagSource.name.like(f"{PREFIX}%"))).all()


def test_seed_kb_creates_sources_and_pending_jobs_once(clean_kb):
    db = clean_kb
    assert seed_kb.seed_kb(db) == DOC_COUNT
    sources = _kb_sources(db)
    assert len(sources) == DOC_COUNT
    jobs = db.scalars(
        select(EmbeddingJob).where(EmbeddingJob.rag_source_id.in_([s.id for s in sources]))
    ).all()
    assert len(jobs) == DOC_COUNT and {j.status for j in jobs} == {"pending"}
    assert agent_config_repo.get(db).rag_enabled is True
    assert seed_kb.seed_kb(db) == 0
    assert len(_kb_sources(db)) == DOC_COUNT


def test_every_doc_is_bilingual():
    docs = sorted(kb_files.KB_DIR.glob("*.md"))
    assert len(docs) == DOC_COUNT
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        assert re.search(r"[\u0980-\u09FF]", text), doc.name
        assert re.search(r"[A-Za-z]", text), doc.name


def test_package_terms_cover_every_active_package():
    text = (kb_files.KB_DIR / "package-terms.md").read_text(encoding="utf-8")
    for code, *_ in seed_telco.PACKAGES:
        assert code in text, code


def test_docs_speak_only_as_telco():
    for doc in sorted(kb_files.KB_DIR.glob("*.md")):
        text = doc.read_text(encoding="utf-8")
        assert not OTHER_BRANDS.findall(text), (doc.name, OTHER_BRANDS.findall(text))
        assert not real_estate_words(text), (doc.name, real_estate_words(text))
        assert "telco" in text, doc.name
