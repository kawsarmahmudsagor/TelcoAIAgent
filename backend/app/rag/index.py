"""Chroma + LlamaIndex plumbing: one cached Chroma client, one cached vector
store per collection, and the OpenRouter embedding model.

Every process (api, scheduler, agent worker) talks to the Chroma *server*
through `chromadb.HttpClient`; the embedded client must not be shared between
processes. Tests swap the client for `chromadb.EphemeralClient()` and the
embedding model for a local fake through the two `set_*_factory` hooks.

Nothing here touches LlamaIndex's global `Settings`: transformations and the
embed model are passed explicitly per call, so the chunk size can change per
ingestion and no OpenAI default is ever constructed by accident.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import chromadb
from llama_index.core import VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore

from app.config import get_settings
from app.rag.config import COLLECTION_BASE, COLLECTION_METADATA

logger = logging.getLogger("rag.index")

ClientFactory = Callable[[], Any]
EmbedModelFactory = Callable[[str, str], BaseEmbedding]


def _http_client() -> Any:
    settings = get_settings()
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)


def _openrouter_embed_model(embedding_model: str, api_key: str) -> BaseEmbedding:
    # OpenAILikeEmbedding, not OpenAIEmbedding: the latter validates `model`
    # against OpenAI's own model names and rejects OpenRouter ids such as
    # google/gemini-embedding-2.
    from llama_index.embeddings.openai_like import OpenAILikeEmbedding

    return OpenAILikeEmbedding(
        model_name=embedding_model,
        api_key=api_key,
        api_base=get_settings().openrouter_base_url,
    )


_lock = threading.Lock()
_client_factory: ClientFactory = _http_client
_embed_model_factory: EmbedModelFactory = _openrouter_embed_model
_client: Any = None
_vector_stores: dict[str, ChromaVectorStore] = {}
_embed_models: dict[tuple[str, str], BaseEmbedding] = {}


def set_client_factory(factory: ClientFactory | None) -> None:
    """Swap how the Chroma client is built (None restores HttpClient). Clears
    every cached client/collection."""
    global _client_factory, _client
    with _lock:
        _client_factory = factory or _http_client
        _client = None
        _vector_stores.clear()


def set_embed_model_factory(factory: EmbedModelFactory | None) -> None:
    """Swap how embedding models are built (None restores OpenRouter)."""
    global _embed_model_factory
    with _lock:
        _embed_model_factory = factory or _openrouter_embed_model
        _embed_models.clear()


def get_client() -> Any:
    global _client
    with _lock:
        if _client is None:
            _client = _client_factory()
        return _client


def get_vector_store(collection: str) -> ChromaVectorStore:
    client = get_client()
    with _lock:
        store = _vector_stores.get(collection)
        if store is None:
            chroma_collection = client.get_or_create_collection(
                collection, metadata=COLLECTION_METADATA
            )
            store = ChromaVectorStore(chroma_collection=chroma_collection)
            _vector_stores[collection] = store
        return store


def get_embed_model(embedding_model: str, api_key: str) -> BaseEmbedding:
    key = (embedding_model, api_key)
    with _lock:
        model = _embed_models.get(key)
        if model is None:
            model = _embed_model_factory(embedding_model, api_key)
            _embed_models[key] = model
        return model


def get_index(collection: str, embedding_model: str, api_key: str) -> VectorStoreIndex:
    return VectorStoreIndex.from_vector_store(
        get_vector_store(collection), embed_model=get_embed_model(embedding_model, api_key)
    )


def transformations(chunk_size: int, chunk_overlap: int) -> list:
    """Markdown headers first, so a Q&A document embeds one chunk per question;
    the sentence splitter then caps anything still longer than chunk_size
    tokens."""
    return [
        MarkdownNodeParser(),
        SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap),
    ]


def _collection_names(client: Any) -> list[str]:
    names = []
    for entry in client.list_collections():
        # chromadb >= 0.6 lists names; older versions list Collection objects.
        names.append(entry if isinstance(entry, str) else entry.name)
    return names


def knowledge_base_collections() -> list[str]:
    """Every existing knowledge-base collection, whichever model wrote it."""
    return [
        name
        for name in _collection_names(get_client())
        if name == COLLECTION_BASE or name.startswith(f"{COLLECTION_BASE}__")
    ]


def delete_where(where: dict, collections: list[str] | None = None) -> int:
    """Deletes every vector matching `where` from the given (default: every
    knowledge-base) collection. Needs no embedding model or API key, so a
    source's vectors can be removed whichever model wrote them. Missing
    collections are skipped, never created. Returns the number removed."""
    client = get_client()
    existing = set(_collection_names(client))
    removed = 0
    for name in collections if collections is not None else knowledge_base_collections():
        if name not in existing:
            continue
        collection = client.get_collection(name)
        ids = collection.get(where=where, include=[]).get("ids") or []
        if ids:
            collection.delete(ids=ids)
            removed += len(ids)
    return removed


def drop_collection(collection: str) -> None:
    """Deletes a whole collection (no-op if it doesn't exist)."""
    client = get_client()
    with _lock:
        _vector_stores.pop(collection, None)
    if collection in _collection_names(client):
        client.delete_collection(collection)
        logger.info("dropped chroma collection %s", collection)


def heartbeat() -> bool:
    """True if the Chroma server answers."""
    try:
        get_client().heartbeat()
        return True
    except Exception:
        # A failed connect leaves a client that may never recover; rebuild next time.
        global _client
        with _lock:
            _client = None
            _vector_stores.clear()
        return False
