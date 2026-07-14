from pathlib import Path

from rag.ingest import KNOWLEDGE_DIR, index_knowledge_base
from rag.retriever import KnowledgeRetriever


def test_rag_indexing_is_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RAG_FORCE_HASH_EMBEDDINGS", "1")
    db_path = tmp_path / "chroma"

    first = index_knowledge_base(db_path=db_path, knowledge_dir=KNOWLEDGE_DIR)
    second = index_knowledge_base(db_path=db_path, knowledge_dir=KNOWLEDGE_DIR)

    assert first.documents == 10
    assert first.chunks > 0
    assert first.added == first.chunks
    assert second.added == 0
    assert second.existing == second.chunks


def test_retrieval_returns_relevant_policy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RAG_FORCE_HASH_EMBEDDINGS", "1")
    db_path = tmp_path / "chroma"
    index_knowledge_base(db_path=db_path, knowledge_dir=KNOWLEDGE_DIR)
    retriever = KnowledgeRetriever(db_path=db_path)

    results = retriever.search_knowledge(
        "How early should I arrive at the airport for a domestic flight?",
        top_k=4,
    )

    assert results
    assert any(
        item.source in {"airport_transfer_guidelines.md", "journey_buffer_rules.md"}
        for item in results
    )
    assert all(item.score >= 0 for item in results)
