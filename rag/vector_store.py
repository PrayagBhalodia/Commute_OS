"""Persistent Chroma storage with local, deterministic embedding fallback."""

from __future__ import annotations

import hashlib
import math
import os
import re
import threading
from pathlib import Path
from typing import Iterable

from rag.schemas import KnowledgeChunk, SearchResult


class LocalEmbedder:
    """Use sentence-transformers when available, otherwise feature hashing.

    Model downloads are opt-in with RAG_ALLOW_MODEL_DOWNLOAD=1. The hashing
    fallback is deterministic, private, and sufficient for offline operation.
    """

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.getenv(
            "RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2"
        )
        self._model = None
        self._model_checked = False
        self._lock = threading.Lock()

    def _load_model(self):
        if self._model_checked:
            return self._model
        truthy = {"1", "true", "yes"}
        force_hashing = os.getenv(
            "RAG_FORCE_HASH_EMBEDDINGS", "0"
        ).lower() in truthy
        use_transformer = os.getenv(
            "RAG_USE_SENTENCE_TRANSFORMERS", "0"
        ).lower() in truthy
        allow_download = os.getenv(
            "RAG_ALLOW_MODEL_DOWNLOAD", "0"
        ).lower() in truthy
        if force_hashing or not (use_transformer or allow_download):
            self._model_checked = True
            return None
        with self._lock:
            if self._model_checked:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(
                    self.model_name,
                    local_files_only=not allow_download,
                )
            except Exception:
                self._model = None
            self._model_checked = True
        return self._model

    @staticmethod
    def _hash_embedding(text: str, dimensions: int = 384) -> list[float]:
        vector = [0.0] * dimensions
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign * (1.0 + min(len(token), 12) / 12.0)
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def encode(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        if model is not None:
            values = model.encode(texts, normalize_embeddings=True)
            return [list(map(float, row)) for row in values]
        return [self._hash_embedding(text) for text in texts]


class ChromaVectorStore:
    collection_name = "dmos_knowledge_v2"

    def __init__(
        self,
        db_path: str | Path | None = None,
        embedder: LocalEmbedder | None = None,
    ) -> None:
        self.db_path = Path(
            db_path or os.getenv("RAG_DB_PATH", "data/chroma")
        )
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or LocalEmbedder()
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is required for RAG; install requirements.txt"
            ) from exc
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return int(self.collection.count())

    def close(self) -> None:
        """Release Chroma's SQLite handle, especially important on Windows."""
        system = getattr(self.client, "_system", None)
        if system is not None and hasattr(system, "stop"):
            system.stop()

    def existing_ids(self, ids: Iterable[str]) -> set[str]:
        values = list(ids)
        if not values:
            return set()
        result = self.collection.get(ids=values, include=[])
        return set(result.get("ids") or [])

    def upsert(self, chunks: list[KnowledgeChunk]) -> tuple[int, int]:
        if not chunks:
            return (0, 0)
        ids = [chunk.chunk_id for chunk in chunks]
        existing = self.existing_ids(ids)
        embeddings = self.embedder.encode([chunk.text for chunk in chunks])
        self.collection.upsert(
            ids=ids,
            documents=[chunk.text for chunk in chunks],
            embeddings=embeddings,
            metadatas=[
                {
                    "source": chunk.source,
                    "category": chunk.category,
                    "section": chunk.section,
                    "updated_at": chunk.updated_at,
                    "title": chunk.title,
                    "region": chunk.region,
                    "operator": chunk.operator,
                    "source_url": chunk.source_url,
                    "source_type": chunk.source_type,
                    "license": chunk.license,
                    "retrieved_at": chunk.retrieved_at,
                    "is_simulated": chunk.is_simulated,
                    "content_hash": chunk.content_hash,
                }
                for chunk in chunks
            ],
        )
        return (len(chunks) - len(existing), len(existing))

    def query(
        self,
        query: str,
        *,
        category: str | None = None,
        top_k: int = 4,
    ) -> list[SearchResult]:
        if not query.strip() or self.count() == 0:
            return []
        where = {"category": category} if category else None
        result = self.collection.query(
            query_embeddings=self.embedder.encode([query]),
            n_results=max(1, min(top_k, 20)),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        output: list[SearchResult] = []
        for chunk_id, text, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            meta = metadata or {}
            score = max(0.0, min(1.0, 1.0 - float(distance)))
            output.append(
                SearchResult(
                    chunk_id=chunk_id,
                    text=text or "",
                    source=str(meta.get("source", "")),
                    category=str(meta.get("category", "")),
                    section=str(meta.get("section", "")),
                    updated_at=str(meta.get("updated_at", "")),
                    title=str(meta.get("title", "")),
                    region=str(meta.get("region", "India")),
                    operator=str(meta.get("operator", "")),
                    source_url=str(meta.get("source_url", "")),
                    source_type=str(meta.get("source_type", "project-authored")),
                    license=str(meta.get("license", "project-generated")),
                    retrieved_at=str(meta.get("retrieved_at", "")),
                    is_simulated=bool(meta.get("is_simulated", False)),
                    content_hash=str(meta.get("content_hash", "")),
                    score=score,
                )
            )
        return output
