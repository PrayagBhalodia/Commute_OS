"""Evaluate English/Hinglish retrieval against the checked-in RAG cases."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from datasets.scripts.common import PROCESSED_DIR, read_jsonl
from rag.ingest import index_knowledge_base
from rag.retriever import KnowledgeRetriever


def evaluate(*, db_path: str | Path | None = None, ensure_index: bool = True) -> dict:
    if ensure_index:
        index_knowledge_base(db_path=db_path)
    retriever = KnowledgeRetriever(db_path=db_path)
    cases = read_jsonl(PROCESSED_DIR / "rag_evaluation.jsonl")
    if not cases:
        from datasets.scripts.build_all import RAG_EVALUATION

        cases = RAG_EVALUATION
    details = []
    for case in cases:
        results = retriever.search_knowledge(case["query"], top_k=4)
        categories = {result.category for result in results}
        hit = bool(categories & set(case["expected_categories"]))
        details.append({
            "id": case["id"],
            "language": case["language"],
            "hit": hit,
            "retrieved_categories": sorted(categories),
        })
    total = len(details)
    return {
        "cases": total,
        "hits": sum(item["hit"] for item in details),
        "retrieval_hit_rate": round(sum(item["hit"] for item in details) / max(1, total), 4),
        "by_language": {
            language: round(
                sum(item["hit"] for item in details if item["language"] == language)
                / max(1, sum(item["language"] == language for item in details)),
                4,
            )
            for language in {item["language"] for item in details}
        },
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()
    print(json.dumps(evaluate(db_path=args.db_path), indent=2))


if __name__ == "__main__":
    main()
