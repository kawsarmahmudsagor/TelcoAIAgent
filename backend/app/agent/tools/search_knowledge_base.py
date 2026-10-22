"""search_knowledge_base: the agent's lookup into the knowledge base (FAQ
documents, crawled pages, text notes, the property listings source).

Built per session from the resolved agent config (top-k, threshold, model,
source scope), and only registered when the knowledge base is enabled -- see
app.agent.entrypoint._session_tools. Listing searches stay with
search_apartments, which queries the database directly.
"""

from __future__ import annotations

import asyncio
import logging

from livekit.agents import RunContext, function_tool

from app.agent.userdata import SessionUserdata
from app.db.session import SessionLocal
from app.rag.config import collection_for
from app.rag.retrieval import retrieve_scored
from app.rag.sanitize import wrap_untrusted_context
from app.services import agent_config_service, rag_service
from app.services.agent_config_service import ResolvedAgentConfig

logger = logging.getLogger("agent.tools.search_knowledge_base")

TOOL_NAME = "search_knowledge_base"
# Never "we don't have that" (see _CONTACT_FALLBACK): agency matters go to the
# team, a property detail gets the listing-doesn't-mention-it exit instead.
_POINT_TO_TEAM = (
    "Don't tell the customer you don't have it or can't say. For an agency matter (policies, "
    "fees, documents, legal steps) point them to the team's phone and head office; for a "
    "detail about a property, follow WHEN YOU DON'T HAVE A DETAIL instead."
)
NOTHING_FOUND = "No relevant information was found in the knowledge base. " + _POINT_TO_TEAM
UNAVAILABLE = "The knowledge base isn't available right now. " + _POINT_TO_TEAM


def search_text(query: str, config: ResolvedAgentConfig) -> str:
    """The tool's answer for `query`: retrieved chunks, each labelled as
    untrusted reference data, or a short "nothing found" line."""
    api_key = agent_config_service.embedding_api_key(config)
    if not api_key:
        logger.warning("knowledge base search skipped: no OpenRouter key for embeddings")
        return UNAVAILABLE

    db = SessionLocal()
    try:
        source_ids = rag_service.searchable_source_ids(db, config.rag_source_ids)
    finally:
        db.close()
    if not source_ids:
        return NOTHING_FOUND

    chunks = retrieve_scored(
        query,
        collection=collection_for(config.embedding_model),
        embedding_model=config.embedding_model,
        api_key=api_key,
        top_k=config.rag_top_k,
        threshold=config.rag_similarity_threshold,
        source_ids=source_ids,
    )
    if not chunks:
        return NOTHING_FOUND
    context = "\n\n".join(
        wrap_untrusted_context(
            chunk["text"],
            str(chunk["metadata"].get("rag_source_name") or "knowledge base"),
            preamble=position == 0,
        )
        for position, chunk in enumerate(chunks)
    )
    return f"{context}\n\nIf these don't answer the question: {_POINT_TO_TEAM}"


def build_search_knowledge_base(config: ResolvedAgentConfig):
    """A search_knowledge_base tool bound to this session's config."""

    @function_tool(name=TOOL_NAME)
    async def search_knowledge_base(ctx: RunContext[SessionUserdata], query: str) -> str:
        """Look up facts about the agency in its knowledge base: policies, fees,
        processes, documents, FAQs and areas covered. Use it before answering any
        question about the agency itself, not for details of a property. Only the
        facts it returns may be stated; if it finds nothing, don't say you lack
        it: point the customer to the team's phone and head office.

        Args:
            query: The customer's question, rephrased as a short standalone search
                query (e.g. "service charge for rentals").
        """
        try:
            return await asyncio.to_thread(search_text, query, config)
        except Exception:
            logger.exception("knowledge base search failed")
            return UNAVAILABLE

    return search_knowledge_base
