"""Knowledge retrieval facade used by API routes and conversational tools."""

from __future__ import annotations

import os
from pathlib import Path

from rag.schemas import SearchResult
from rag.vector_store import ChromaVectorStore


class KnowledgeRetriever:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.store = ChromaVectorStore(db_path=db_path)

    def search_knowledge(
        self,
        query: str,
        category: str | None = None,
        top_k: int | None = None,
    ) -> list[SearchResult]:
        limit = top_k or int(os.getenv("RAG_TOP_K", "4"))
        return self.store.query(query, category=category, top_k=limit)

    def close(self) -> None:
        self.store.close()


_default_retriever: KnowledgeRetriever | None = None


def search_knowledge(
    query: str,
    category: str | None = None,
    top_k: int = 4,
) -> list[SearchResult]:
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = KnowledgeRetriever()
    return _default_retriever.search_knowledge(query, category, top_k)
