"""A deterministic, offline stand-in for the OpenRouter embedding model."""

import hashlib
import math
import re

from llama_index.core.base.embeddings.base import BaseEmbedding

DIM = 256


def _vector(text: str) -> list[float]:
    """Hashed bag of words, L2-normalised: texts sharing words point the same
    way, so cosine retrieval behaves sensibly in tests."""
    vector = [0.0] * DIM
    vector[0] = 0.01  # never all-zero
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        vector[1 + int(hashlib.md5(word.encode()).hexdigest(), 16) % (DIM - 1)] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


class HashEmbedding(BaseEmbedding):
    def _get_query_embedding(self, query: str) -> list[float]:
        return _vector(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return _vector(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return _vector(text)
