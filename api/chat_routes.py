"""FastAPI routes for conversational DMOS and local RAG."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from llm.conversation_agent import ConversationAgent
from llm.conversation_memory import ConversationMemory
from llm.schemas import (
    ChatMessageRequest,
    ChatMessageResponse,
    RagReindexRequest,
    RagSearchRequest,
)
from llm.tool_registry import ToolRegistry
from orchestration.orchestrator import DMOSOrchestrator
from rag.ingest import index_knowledge_base
from rag.retriever import KnowledgeRetriever


def build_chat_router(
    orchestrator: DMOSOrchestrator,
    *,
    rag_db_path: str | Path | None = None,
    chat_db_path: str | Path | None = None,
) -> tuple[APIRouter, dict[str, Any]]:
    router = APIRouter()
    retriever = KnowledgeRetriever(db_path=rag_db_path)
    registry = ToolRegistry(orchestrator, retriever)
    # Persist chat sessions so an API restart doesn't strand users
    # mid-conversation with a session_id the server no longer knows.
    memory = ConversationMemory(
        db_path=str(chat_db_path)
        if chat_db_path
        else os.environ.get("COMMUTE_CHAT_DB", "data/chat_sessions.db")
    )
    agent = ConversationAgent(registry, memory=memory)

    @router.post("/chat/message", response_model=ChatMessageResponse)
    def chat_message(body: ChatMessageRequest) -> ChatMessageResponse:
        try:
            return agent.handle(body)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/chat/sessions/{session_id}")
    def get_chat_session(session_id: str):
        state = memory.get(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return state

    @router.delete("/chat/sessions/{session_id}")
    def delete_chat_session(session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "deleted": memory.delete(session_id)}

    @router.post("/rag/search")
    def rag_search(body: RagSearchRequest) -> dict[str, Any]:
        results = retriever.search_knowledge(
            body.query, body.category, body.top_k
        )
        return {
            "query": body.query,
            "results": [item.model_dump(mode="json") for item in results],
        }

    @router.post("/rag/reindex")
    def rag_reindex(body: RagReindexRequest) -> dict[str, Any]:
        # Upsert-by-content-id is idempotent. Rebuild is retained in the API
        # contract for future corpus deletion but never destroys data silently.
        stats = index_knowledge_base(db_path=retriever.store.db_path)
        return {
            **stats.model_dump(mode="json"),
            "rebuild_requested": body.rebuild,
        }

    return router, {
        "agent": agent,
        "memory": memory,
        "registry": registry,
        "retriever": retriever,
    }
