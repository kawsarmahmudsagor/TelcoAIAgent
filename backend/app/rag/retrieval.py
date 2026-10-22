"""Scored retrieval over a knowledge-base collection.

`retrieve_scored` is sync (the API's retrieval tester and the job code run in
threads already); the agent tool uses `aretrieve_scored`, which runs it in a
worker thread so the voice loop never blocks on the embedding call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any, TypedDict

from llama_index.core.schema import MetadataMode
from llama_index.core.vector_stores.types import FilterOperator, MetadataFilter, MetadataFilters

from app.rag.config import RAG_SOURCE_ID_KEY
from app.rag.index import get_index


class ScoredChunk(TypedDict):
    node_id: str
    text: str
    # exp(-cosine distance): 1.0 = identical direction, ~0.37 = orthogonal.
    score: float | None
    metadata: dict[str, Any]


def retrieve_scored(
    query: str,
    *,
    collection: str,
    embedding_model: str,
    api_key: str,
    top_k: int = 5,
    threshold: float = 0.0,
    source_ids: Iterable[str] | None = None,
) -> list[ScoredChunk]:
    """The `top_k` chunks most similar to `query` scoring at least `threshold`.

    `source_ids` restricts retrieval to those rag_sources (every chunk carries
    rag_source_id); an empty iterable means "nothing selected" and returns
    nothing, None means no filter. `embedding_model` must be the model that
    wrote `collection`, or the query lands in the wrong vector space.
    """
    ids = None if source_ids is None else [str(value) for value in source_ids]
    if ids is not None and not ids:
        return []
    if not query.strip():
        return []

    filters = None
    if ids:
        filters = MetadataFilters(
            filters=[MetadataFilter(key=RAG_SOURCE_ID_KEY, value=ids, operator=FilterOperator.IN)]
        )
    retriever = get_index(collection, embedding_model, api_key).as_retriever(
        similarity_top_k=top_k, filters=filters
    )
    chunks = [
        ScoredChunk(
            node_id=hit.node.node_id,
            text=hit.node.get_content(metadata_mode=MetadataMode.NONE),
            score=hit.score,
            metadata=dict(hit.node.metadata or {}),
        )
        for hit in retriever.retrieve(query)
    ]
    return [chunk for chunk in chunks if chunk["score"] is None or chunk["score"] >= threshold]


async def aretrieve_scored(query: str, **kwargs: Any) -> list[ScoredChunk]:
    return await asyncio.to_thread(retrieve_scored, query, **kwargs)
