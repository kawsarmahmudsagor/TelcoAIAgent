pytest_plugins = ["bss_helpers"]

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_admin, get_current_subscriber
from app.main import app


@pytest.fixture
def api():
    """Client with admin auth overridden."""
    app.dependency_overrides[get_current_admin] = lambda: "pytest"
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_admin, None)


@pytest.fixture
def customer_api():
    """Factory: customer_api(subscriber_id) -> client signed in as that subscriber."""

    def make(subscriber_id):
        app.dependency_overrides[get_current_subscriber] = lambda: subscriber_id
        return TestClient(app)

    yield make
    app.dependency_overrides.pop(get_current_subscriber, None)


@pytest.fixture
def anon_api():
    """Client with no session cookie and no auth override, for 401 checks."""
    app.dependency_overrides.pop(get_current_admin, None)
    return TestClient(app)


@pytest.fixture
def rag_fakes(monkeypatch):
    """Knowledge-base tests without a Chroma server or an API key: an in-memory
    Chroma (chromadb.EphemeralClient, emptied first) and a deterministic local
    bag-of-words embedding, injected through app.rag.index's factories."""
    import chromadb

    from app.rag import index as rag_index
    from app.rag import jobs as rag_jobs
    from app.services import agent_config_service
    from fake_embedding import HashEmbedding

    client = chromadb.EphemeralClient()
    for entry in client.list_collections():
        client.delete_collection(entry if isinstance(entry, str) else entry.name)
    rag_index.set_client_factory(lambda: client)
    rag_index.set_embed_model_factory(lambda model, key: HashEmbedding(model_name=model))
    monkeypatch.setattr(agent_config_service, "embedding_api_key", lambda *a, **k: "test-key")
    monkeypatch.setattr(rag_jobs, "embedding_key", lambda config: "test-key")
    yield client
    rag_index.set_client_factory(None)
    rag_index.set_embed_model_factory(None)


@pytest.fixture
def db():
    """A plain SQLAlchemy session; rolled back and closed afterwards."""
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
