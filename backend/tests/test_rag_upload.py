"""The knowledge-base API: multipart upload, validation, the job round trip
through the API, and 401s without a session."""

import uuid

import pytest
from sqlalchemy import text, update

from app.config import get_settings
from app.db.session import SessionLocal
from app.models.rag import EmbeddingJob
from app.rag import jobs as rag_jobs
from app.rag.config import MAX_UPLOAD_BYTES

PREFIX = "pytest-kb-upload-"
FAQ_MD = b"""# Fees

### What is the service charge for rentals?
One month's rent, paid when the lease is signed.

### Can I pay the deposit in instalments?
Yes, in up to three monthly instalments.
"""


@pytest.fixture(autouse=True)
def _uploads_and_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
    yield
    db = SessionLocal()
    try:
        db.execute(text("delete from rag_sources where name like :p"), {"p": PREFIX + "%"})
        db.commit()
    finally:
        db.close()


def _upload(api, filename: str, content: bytes, name: str = "fees"):
    return api.post(
        "/api/rag/sources/documents",
        files={"file": (filename, content, "text/markdown")},
        data={"name": PREFIX + name},
    )


def _run(job_id: str) -> str:
    db = SessionLocal()
    try:
        db.execute(update(EmbeddingJob).where(EmbeddingJob.id == uuid.UUID(job_id)).values(priority=-1_000_000))
        db.commit()
        claimed = rag_jobs.claim_next_job(db)
        assert claimed is not None and str(claimed.id) == job_id
    finally:
        db.close()
    return rag_jobs.run_job(uuid.UUID(job_id))


def test_document_upload_returns_201_and_stores_the_file(api, tmp_path):
    response = _upload(api, "fees.md", FAQ_MD)
    assert response.status_code == 201, response.text
    body = response.json()
    source = body["source"]
    assert source["status"] == "pending" and source["source_type"] == "document"
    assert source["filename"] == "fees.md" and source["size_bytes"] == len(FAQ_MD)
    assert body["job"]["job_type"] == "ingest" and body["job"]["status"] == "pending"
    assert (tmp_path / "rag" / source["id"] / "fees.md").read_bytes() == FAQ_MD

    listed = api.get("/api/rag/sources").json()
    assert any(item["id"] == source["id"] for item in listed["items"])

    assert api.delete(f"/api/rag/sources/{source['id']}").status_code == 204
    assert not (tmp_path / "rag" / source["id"]).exists()
    assert api.get(f"/api/rag/sources/{source['id']}").status_code == 404


def test_upload_rejects_bad_type_and_oversize(api):
    assert _upload(api, "malware.exe", b"MZ").status_code == 400
    assert _upload(api, "empty.md", b"").status_code == 400
    too_big = _upload(api, "huge.txt", b"a" * (MAX_UPLOAD_BYTES + 1))
    assert too_big.status_code == 413


def test_uploaded_document_round_trip_through_the_api(api, rag_fakes):
    created = _upload(api, "fees.md", FAQ_MD).json()
    source_id = created["source"]["id"]
    assert _run(created["job"]["id"]) == "succeeded"

    detail = api.get(f"/api/rag/sources/{source_id}").json()
    assert detail["status"] == "ready" and detail["chunk_count"] >= 2
    assert detail["jobs"][0]["status"] == "succeeded"

    search = api.post(
        "/api/rag/search",
        json={"query": "deposit instalments", "threshold": 0, "source_ids": [source_id]},
    )
    assert search.status_code == 200, search.text
    results = search.json()["results"]
    assert results and "instalments" in results[0]["text"]
    assert results[0]["rag_source_id"] == source_id

    reindex = api.post(f"/api/rag/sources/{source_id}/reindex")
    assert reindex.status_code == 202 and reindex.json()["job"]["job_type"] == "reindex"
    assert _run(reindex.json()["job"]["id"]) == "succeeded"


def test_text_and_link_sources_validate_input(api):
    text_source = api.post("/api/rag/sources/text", json={"name": PREFIX + "note", "text": "Open 10-7."})
    assert text_source.status_code == 201
    assert text_source.json()["source"]["source_type"] == "text"
    assert api.post("/api/rag/sources/text", json={"name": PREFIX + "x", "text": "   "}).status_code == 400

    link = api.post(
        "/api/rag/sources/links",
        json={"url": "https://example.com/", "name": PREFIX + "site", "max_depth": 1, "max_pages": 5},
    )
    assert link.status_code == 201
    assert link.json()["source"]["config"]["max_pages"] == 5
    bad = api.post("/api/rag/sources/links", json={"url": "file:///etc/passwd", "name": PREFIX + "bad"})
    assert bad.status_code == 400


def test_rag_status_and_summary_report_the_knowledge_base(api):
    status = api.get("/api/dashboard/rag-status")
    assert status.status_code == 200
    body = status.json()
    assert {"embedding_ready", "chroma_reachable", "sources", "total_chunks"} <= set(body)
    assert isinstance(api.get("/api/agent-config").json()["embedding_ready"], bool)
    summary = api.get("/api/dashboard/summary").json()
    assert summary["kb_sources_total"] >= summary["kb_sources_ready"] >= 0


def test_retry_unknown_job_is_404(api):
    assert api.post(f"/api/rag/jobs/{uuid.uuid4()}/retry").status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/rag/sources"),
        ("post", "/api/rag/sources/documents"),
        ("post", "/api/rag/sources/links"),
        ("post", "/api/rag/sources/text"),
        ("get", f"/api/rag/sources/{uuid.uuid4()}"),
        ("delete", f"/api/rag/sources/{uuid.uuid4()}"),
        ("post", f"/api/rag/sources/{uuid.uuid4()}/reindex"),
        ("post", "/api/rag/reindex-all"),
        ("get", "/api/rag/jobs"),
        ("post", f"/api/rag/jobs/{uuid.uuid4()}/retry"),
        ("post", "/api/rag/search"),
        ("post", "/api/agent-config/migrate-embedding"),
        ("get", "/api/dashboard/rag-status"),
    ],
)
def test_knowledge_base_routes_require_auth(anon_api, method, path):
    assert getattr(anon_api, method)(path).status_code == 401


def test_agent_config_source_scope(api):
    before = api.get("/api/agent-config").json()["rag_source_ids"]
    source_id = api.post(
        "/api/rag/sources/text", json={"name": PREFIX + "scope", "text": "Scoped note."}
    ).json()["source"]["id"]
    try:
        scoped = api.patch("/api/agent-config", json={"rag_source_ids": [source_id]})
        assert scoped.status_code == 200 and scoped.json()["rag_source_ids"] == [source_id]
        unknown = api.patch("/api/agent-config", json={"rag_source_ids": [str(uuid.uuid4())]})
        assert unknown.status_code == 422
        # Deleting the source drops it from the scope too.
        api.delete(f"/api/rag/sources/{source_id}")
        assert source_id not in api.get("/api/agent-config").json()["rag_source_ids"]
    finally:
        api.patch("/api/agent-config", json={"rag_source_ids": before})
