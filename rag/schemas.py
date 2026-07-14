"""Pydantic contracts for local knowledge ingestion and retrieval."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeChunk(BaseModel):
    chunk_id: str
    text: str
    source: str
    category: str
    section: str
    updated_at: str


class SearchResult(BaseModel):
    chunk_id: str
    text: str
    source: str
    category: str
    section: str
    updated_at: str
    score: float = Field(ge=0.0, le=1.0)


class IndexStats(BaseModel):
    documents: int
    chunks: int
    added: int
    existing: int
    indexed_at: datetime
