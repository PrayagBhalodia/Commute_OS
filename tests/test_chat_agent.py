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


def complete_plan(agent, *, user_id: str, message: str):
    response = agent.handle(ChatMessageRequest(user_id=user_id, message=message))
    assert response.state.status == "waiting_for_start_time"
    response = agent.handle(ChatMessageRequest(session_id=response.session_id, user_id=user_id, message="9:00 AM"))
    assert response.state.status == "waiting_for_return"
    response = agent.handle(ChatMessageRequest(session_id=response.session_id, user_id=user_id, message="No, this is one way"))
    assert response.state.status == "waiting_for_preference_choice"
    return agent.handle(
        ChatMessageRequest(
            session_id=response.session_id,
            user_id=user_id,
            message="Use my usual saved preferences",
        )
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
    response = complete_plan(
        agent,
        user_id="chat-plan",
        message=(
            "Plan a trip from Ahmedabad to Jio Institute tomorrow "
            "with one suitcase, fastest route."
        ),
    )

    assert response.state.active_trip_id
    assert response.state.status == "choosing_route"
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
    assert second.state.status == "waiting_for_start_time"
    assert "time" in second.message.lower()


def test_route_then_leg_selection_composes_review(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    planned = complete_plan(
        agent,
        user_id="chat-legs",
        message="Plan a trip from Ahmedabad to Jio Institute tomorrow",
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
    assert reviewed.state.status == "waiting_for_wallet_topup"
    assert any(item["tool"] == "compose_journey" for item in reviewed.tool_results)
    assert any(item["tool"] == "get_wallet_balance" for item in reviewed.tool_results)
    assert any(action.href == "/wallet" for action in reviewed.suggested_actions)


def test_sufficient_wallet_hands_off_to_booking_review(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    agent.registry.orchestrator.wallet.topup(
        "chat-funded", 100000, "wallet", idempotency_key="funded-test"
    )
    planned = complete_plan(
        agent,
        user_id="chat-funded",
        message="Plan a trip from Ahmedabad to Jio Institute tomorrow",
    )
    route = agent.handle(
        ChatMessageRequest(
            session_id=planned.session_id,
            user_id="chat-funded",
            message="Option 1",
        )
    )
    reviewed = agent.handle(
        ChatMessageRequest(
            session_id=route.session_id,
            user_id="chat-funded",
            message="Review journey",
        )
    )

    assert reviewed.state.status == "ready_for_booking_review"
    assert any(
        action.href == f"/booking/{reviewed.state.active_trip_id}"
        for action in reviewed.suggested_actions
    )


def test_custom_preferences_require_every_leg_choice(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    first = agent.handle(
        ChatMessageRequest(
            user_id="chat-custom",
            message="Plan from Ahmedabad to Jio Institute tomorrow at 9 AM, one way",
        )
    )
    assert first.state.status == "waiting_for_preference_choice"
    planned = agent.handle(
        ChatMessageRequest(
            session_id=first.session_id,
            user_id="chat-custom",
            message="I want custom preferences for this trip",
        )
    )
    route = agent.handle(
        ChatMessageRequest(
            session_id=planned.session_id,
            user_id="chat-custom",
            message="Option 1",
        )
    )
    assert route.leg_option_groups
    assert not any(action.id == "review_journey" for action in route.suggested_actions)

    response = route
    for group in route.leg_option_groups:
        response = agent.handle(
            ChatMessageRequest(
                session_id=route.session_id,
                user_id="chat-custom",
                message=f"Leg {group['leg_number']} option 1",
            )
        )
    assert response.journey_review is not None
    assert len(response.state.selected_leg_ids) == len(route.leg_option_groups)


def test_hinglish_route_invokes_plan_tool(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    response = agent.handle(
        ChatMessageRequest(
            user_id="chat-hinglish",
            message="Ahmedabad se Jio Institute jana hai, sabse sasta option batao",
        )
    )

    assert response.state.constraints.origin == "Ahmedabad"
    assert response.state.constraints.destination == "Jio Institute"
    assert response.state.constraints.preference_weights["cost"] == 1.0
    assert response.state.status == "waiting_for_start_date"
    assert not response.tool_results


class FailingClient:
    enabled = True

    def respond(self, **kwargs):
        return None


def test_llm_failure_uses_fallback_mode(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch, client=FailingClient())
    response = agent.handle(
        ChatMessageRequest(user_id="chat-fallback", message="What can you help me with?")
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
