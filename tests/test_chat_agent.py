from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.chat_routes import build_chat_router
from llm.client import ProviderResponse, ProviderToolCall
from llm.conversation_agent import ConversationAgent
from llm.conversation_memory import ConversationMemory
from llm.schemas import AutonomyLevel, ChatMessageRequest
from llm.tool_registry import ToolRegistry
from orchestration.orchestrator import DMOSOrchestrator
from rag.ingest import KNOWLEDGE_DIR, index_knowledge_base
from rag.retriever import KnowledgeRetriever


def make_agent(tmp_path: Path, monkeypatch, client=None):
    monkeypatch.setenv("RAG_FORCE_HASH_EMBEDDINGS", "1")
    rag_path = tmp_path / "chroma"
    index_knowledge_base(db_path=rag_path, knowledge_dir=KNOWLEDGE_DIR)
    orchestrator = DMOSOrchestrator(
        wallet_db=str(tmp_path / "wallet.db"),
        booking_db=str(tmp_path / "booking.db"),
        profiles_db=str(tmp_path / "profiles.db"),
    )
    registry = ToolRegistry(orchestrator, KnowledgeRetriever(rag_path))
    return ConversationAgent(
        registry,
        memory=ConversationMemory(),
        client=client,
    )


def test_policy_question_uses_rag(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    response = agent.handle(
        ChatMessageRequest(
            user_id="chat-policy",
            message="How early should I arrive at the airport?",
        )
    )

    assert response.citations
    assert any(item.event == "knowledge_retrieved" for item in response.execution_trace)
    assert response.tool_results[0]["tool"] == "search_knowledge"


def test_planning_request_invokes_plan_tool(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    response = agent.handle(
        ChatMessageRequest(
            user_id="chat-plan",
            message=(
                "Plan a trip from Ahmedabad to Jio Institute tomorrow "
                "with one suitcase, fastest route."
            ),
        )
    )

    assert response.state.active_trip_id
    assert response.state.status == "waiting_for_consent"
    assert any(item["tool"] == "plan_journey" for item in response.tool_results)
    assert any(item.event == "journey_planned" for item in response.execution_trace)


def test_origin_choice_requires_explicit_location_share(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    first = agent.handle(
        ChatMessageRequest(
            user_id="chat-location",
            message="I need to travel to Mumbai Airport tomorrow",
        )
    )

    assert first.state.status == "awaiting_origin_choice"
    assert {action.kind for action in first.suggested_actions} >= {"location", "message"}
    assert first.state.constraints.destination == "Mumbai Airport"

    second = agent.handle(
        ChatMessageRequest(
            session_id=first.session_id,
            user_id="chat-location",
            message="Use my current location",
            current_lat=23.0225,
            current_lng=72.5714,
            current_location_label="Current location",
        )
    )
    assert second.state.constraints.origin == "Current location"
    assert second.state.constraints.origin_lat == 23.0225
    assert any(action.id == "plan_now" for action in second.suggested_actions)


def test_route_then_leg_selection_composes_review(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    planned = agent.handle(
        ChatMessageRequest(
            user_id="chat-legs",
            message="Plan a trip from Ahmedabad to Jio Institute tomorrow",
        )
    )
    route = agent.handle(
        ChatMessageRequest(
            session_id=planned.session_id,
            user_id="chat-legs",
            message="Option 1",
        )
    )
    assert route.state.status == "choosing_legs"
    assert route.leg_option_groups

    reviewed = agent.handle(
        ChatMessageRequest(
            session_id=planned.session_id,
            user_id="chat-legs",
            message="Leg 1 option 1",
        )
    )
    assert reviewed.journey_review is not None
    assert reviewed.state.status == "waiting_for_consent"
    assert any(item["tool"] == "compose_journey" for item in reviewed.tool_results)


class FailingClient:
    enabled = True

    def respond(self, **kwargs):
        return None


def test_llm_failure_uses_fallback_mode(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch, client=FailingClient())
    response = agent.handle(
        ChatMessageRequest(user_id="chat-fallback", message="Hello there")
    )

    assert response.mode == "deterministic_fallback"
    assert any(item.event == "llm_fallback" for item in response.execution_trace)


class HallucinatingBookingClient:
    enabled = True

    def respond(self, **kwargs):
        return ProviderResponse(
            text="I will book it.",
            tool_calls=[
                ProviderToolCall(
                    name="confirm_booking",
                    arguments={
                        "trip_id": "invented",
                        "itinerary_id": "invented",
                        "user_id": "manual-user",
                        "user_confirmed": True,
                    },
                )
            ],
        )


def test_manual_autonomy_blocks_automatic_booking(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch, client=HallucinatingBookingClient())
    response = agent.handle(
        ChatMessageRequest(
            user_id="manual-user",
            message="That looks interesting",
            autonomy_level=AutonomyLevel.MANUAL,
        )
    )

    assert not response.tool_results
    assert any(
        item.event == "waiting_for_consent" and item.status == "blocked"
        for item in response.execution_trace
    )


def test_chat_and_rag_api_session_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_FORCE_HASH_EMBEDDINGS", "1")
    orchestrator = DMOSOrchestrator(
        wallet_db=str(tmp_path / "api-wallet.db"),
        booking_db=str(tmp_path / "api-booking.db"),
        profiles_db=str(tmp_path / "api-profiles.db"),
    )
    router, _ = build_chat_router(
        orchestrator, rag_db_path=tmp_path / "api-chroma"
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    indexed = client.post("/rag/reindex", json={})
    assert indexed.status_code == 200
    searched = client.post(
        "/rag/search",
        json={"query": "airport arrival buffer", "top_k": 2},
    )
    assert searched.status_code == 200
    assert searched.json()["results"]

    chat = client.post(
        "/chat/message",
        json={"user_id": "api-user", "message": "What is the baggage policy?"},
    )
    assert chat.status_code == 200
    session_id = chat.json()["session_id"]
    assert client.get(f"/chat/sessions/{session_id}").status_code == 200
    deleted = client.delete(f"/chat/sessions/{session_id}")
    assert deleted.json()["deleted"] is True
    assert client.get(f"/chat/sessions/{session_id}").status_code == 404
