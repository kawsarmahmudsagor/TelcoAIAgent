"""Shared constants for the knowledge-base (RAG) pipeline."""

import re

COLLECTION_BASE = "knowledge_base"

ALLOWED_EXTENSIONS = frozenset({".md", ".txt", ".pdf", ".xlsx", ".json"})
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

# Chroma's default space is L2; the vector store turns a distance into a score
# with exp(-distance), which only lands in a meaningful 0..1 range for cosine
# distance (0..2 -> score 1.0..0.135). Every collection is created with this.
COLLECTION_METADATA = {"hnsw:space": "cosine"}

# Metadata keys every chunk carries, so retrieval can filter by source and a
# source's vectors can be deleted without knowing their doc ids.
RAG_SOURCE_ID_KEY = "rag_source_id"
RAG_SOURCE_PAGE_ID_KEY = "rag_source_page_id"


def collection_for(embedding_model: str) -> str:
    """The Chroma collection holding vectors from `embedding_model`.

    Vectors from different models aren't comparable (and usually differ in
    dimension), so every model gets its own suffixed collection -- including
    the default one, so changing the default never mixes two models' vectors.
    """
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", embedding_model.strip())
    return f"{COLLECTION_BASE}__{slug}"
