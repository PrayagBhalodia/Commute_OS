import json
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
    # Keep unit tests offline: place classification/geocoding falls back to
    # the bundled catalog instead of calling LocationIQ/Nominatim.
    monkeypatch.setenv("DMOS_USE_NOMINATIM", "0")
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
        )
    )
    # Coordinates resolve to the real place name (offline catalog: Ahmedabad),
    # never the generic "Current location" label.
    assert second.state.constraints.origin == "Ahmedabad"
    assert second.state.constraints.origin_lat == 23.0225
    assert "Ahmedabad" in second.message
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


class ScriptedChatClient:
    """Simulates a Gemini/ChatGPT wrapper: returns queued JSON slot-fills."""

    enabled = True

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def chat(self, *, messages):
        self.calls += 1
        return json.dumps(self._responses.pop(0))


def test_llm_wrapper_collects_slots_one_at_a_time(tmp_path, monkeypatch):
    client = ScriptedChatClient(
        [
            {"slots": {}, "reply": "Where are you starting from?"},
            {"slots": {"origin": "Ahmedabad"}, "reply": "Where to?"},
            {"slots": {"destination": "Jio Institute"}, "reply": "What date?"},
            {"slots": {"start_date": "2026-08-01"}, "reply": "What time?"},
            {"slots": {"start_time": "9 am"}, "reply": "Return journey?"},
            {"slots": {"return_required": True}, "reply": "Return starts where?"},
            {"slots": {"return_origin": "Jio Institute"}, "reply": "Return ends where?"},
            {"slots": {"return_destination": "Gandhinagar"}, "reply": "Return date?"},
            {"slots": {"return_date": "2026-08-05"}, "reply": "Return time?"},
            {"slots": {"return_time": "6 pm"}, "reply": "All set!"},
        ]
    )
    agent = make_agent(tmp_path, monkeypatch, client=client)
    messages = [
        "I want to plan a trip",
        "From Ahmedabad",
        "Jio Institute",
        "August 1st",
        "9 am",
        "Yes I need to come back",
        "Same as Jio Institute",
        "Gandhinagar",  # return ends somewhere different from the origin
        "August 5th",
        "6 pm",
    ]
    expected_status = [
        "waiting_for_origin",
        "waiting_for_destination",
        "waiting_for_start_date",
        "waiting_for_start_time",
        "waiting_for_return",
        "waiting_for_return_origin",
        "waiting_for_return_destination",
        "waiting_for_return_date",
        "waiting_for_return_time",
        "waiting_for_preference_choice",
    ]
    session_id = None
    response = None
    for message, status in zip(messages, expected_status):
        response = agent.handle(
            ChatMessageRequest(session_id=session_id, user_id="wrap", message=message)
        )
        session_id = response.session_id
        assert response.mode == "llm"
        assert response.state.status == status

    c = response.state.constraints
    assert (c.origin, c.destination, c.start_date, c.start_time) == (
        "Ahmedabad",
        "Jio Institute",
        "2026-08-01",
        "9 am",
    )
    assert c.return_required is True
    assert c.return_origin == "Jio Institute"
    assert c.return_destination == "Gandhinagar"
    assert (c.return_date, c.return_time) == ("2026-08-05", "6 pm")

    # Handing off to the deterministic planning path still works.
    planned = agent.handle(
        ChatMessageRequest(
            session_id=session_id,
            user_id="wrap",
            message="Use my usual saved preferences",
        )
    )
    assert planned.state.status == "choosing_route"
    assert planned.state.active_trip_id


def test_llm_wrapper_extracts_full_first_prompt(tmp_path, monkeypatch):
    client = ScriptedChatClient(
        [
            {
                "slots": {
                    "origin": "Ahmedabad",
                    "destination": "Jio Institute",
                    "start_date": "2026-08-01",
                    "start_time": "9 am",
                },
                "reply": "Do you need a return journey?",
            }
        ]
    )
    agent = make_agent(tmp_path, monkeypatch, client=client)
    response = agent.handle(
        ChatMessageRequest(
            user_id="wrap-full",
            message="Plan Ahmedabad to Jio Institute on 2026-08-01 at 9 am",
        )
    )
    assert response.mode == "llm"
    # Everything was extracted from one prompt; only the return flag is missing.
    assert response.state.status == "waiting_for_return"
    assert response.state.constraints.origin == "Ahmedabad"
    assert response.state.constraints.start_time == "9 am"


def test_llm_wrapper_bad_json_falls_back(tmp_path, monkeypatch):
    class GarbageChatClient:
        enabled = True

        def chat(self, *, messages):
            return "sorry I can't do that"  # not JSON

    agent = make_agent(tmp_path, monkeypatch, client=GarbageChatClient())
    response = agent.handle(
        ChatMessageRequest(user_id="wrap-bad", message="Plan a trip to Mumbai Airport")
    )
    # Unusable LLM output → deterministic controller takes over cleanly.
    assert any(item.event == "llm_fallback" for item in response.execution_trace)
    assert response.state.constraints.destination == "Mumbai Airport"


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
        orchestrator,
        rag_db_path=tmp_path / "api-chroma",
        chat_db_path=tmp_path / "api-chat.db",
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


def stub_place_classifier(monkeypatch, mapping):
    """Replace the live geocoder-backed classifier with a canned mapping,
    mirroring what LocationIQ/Nominatim would return for these names."""

    def fake_classify(text: str) -> str:
        return mapping.get((text or "").strip().lower(), "unknown")

    monkeypatch.setattr("llm.conversation_agent.classify_place", fake_classify)


def test_state_destination_drills_to_city_then_locality(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    stub_place_classifier(
        monkeypatch,
        {"gujarat": "state", "ahmedabad": "city", "navrangpura": "specific"},
    )
    response = agent.handle(
        ChatMessageRequest(user_id="drill", message="I have to travel to Gujarat")
    )
    assert "where in Gujarat" in response.message
    assert response.state.status == "waiting_for_destination"

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id, user_id="drill", message="Ahmedabad"
        )
    )
    assert "Where in Ahmedabad" in response.message
    assert response.state.status == "waiting_for_destination"

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id, user_id="drill", message="Navrangpura"
        )
    )
    assert response.state.constraints.destination == "Navrangpura"
    assert response.state.status != "waiting_for_destination"


def test_country_destination_prompts_narrowing(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    stub_place_classifier(monkeypatch, {"japan": "country"})
    response = agent.handle(
        ChatMessageRequest(user_id="drill-country", message="I want to travel to Japan")
    )
    assert "where in Japan" in response.message
    assert "country" in response.message
    assert response.state.status == "waiting_for_destination"


def test_broad_destination_accepted_when_user_insists(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    stub_place_classifier(monkeypatch, {"goa": "state"})
    response = agent.handle(
        ChatMessageRequest(user_id="drill2", message="I need to go to Goa")
    )
    assert "where in Goa" in response.message

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id, user_id="drill2", message="Just Goa is fine"
        )
    )
    assert response.state.constraints.destination == "Goa"
    assert response.state.status != "waiting_for_destination"


def test_specific_destination_skips_drilling(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    stub_place_classifier(monkeypatch, {"jio institute": "specific"})
    response = agent.handle(
        ChatMessageRequest(
            user_id="drill3",
            message="I need to reach Jio Institute from Ahmedabad tomorrow",
        )
    )
    assert "where in" not in response.message.lower()


def test_llm_wrapper_pinpoints_broad_destination(tmp_path, monkeypatch):
    # Regression: the LLM slot-filler accepts a whole state as the destination
    # and tries to move on to the origin. Pin-pointing must interrupt and drill
    # state -> city -> locality, then accept and pin the specific place so it is
    # never re-asked while the remaining slots are collected.
    client = ScriptedChatClient(
        [
            {"slots": {"destination": "Gujarat"}, "reply": "Where are you starting from?"},
            {"slots": {"destination": "Ahmedabad"}, "reply": "Where are you starting from?"},
            {"slots": {"destination": "Navrangpura"}, "reply": "Where are you starting from?"},
        ]
    )
    agent = make_agent(tmp_path, monkeypatch, client=client)
    stub_place_classifier(
        monkeypatch,
        {"gujarat": "state", "ahmedabad": "city", "navrangpura": "specific"},
    )

    # A whole state overrides the LLM's "where are you starting from?".
    response = agent.handle(ChatMessageRequest(user_id="pin", message="Gujarat"))
    assert "where in Gujarat" in response.message
    assert response.state.status == "waiting_for_destination"

    # A city is still broad -> drill one more level.
    response = agent.handle(
        ChatMessageRequest(session_id=response.session_id, user_id="pin", message="Ahmedabad")
    )
    assert "Where in Ahmedabad" in response.message
    assert response.state.status == "waiting_for_destination"

    # A specific locality is accepted, pinned, and the flow moves past destination.
    response = agent.handle(
        ChatMessageRequest(session_id=response.session_id, user_id="pin", message="Navrangpura")
    )
    assert "where in" not in response.message.lower()
    assert response.state.constraints.destination == "Navrangpura"
    assert response.state.constraints.destination_pinned == "Navrangpura"
    assert response.state.status != "waiting_for_destination"


def test_broad_return_destination_is_pinpointed(tmp_path, monkeypatch):
    # The trip's final endpoint (return destination) is drilled down the same
    # way as the onward destination, independently pinned.
    client = ScriptedChatClient(
        [
            {"slots": {}, "reply": "Where should your return journey start?"},
            {"slots": {"return_origin": "Jio Institute"}, "reply": "Where should it end?"},
            {"slots": {"return_destination": "Gujarat"}, "reply": "What date is the return?"},
            {"slots": {"return_destination": "Gandhinagar"}, "reply": "What date is the return?"},
        ]
    )
    agent = make_agent(tmp_path, monkeypatch, client=client)
    stub_place_classifier(monkeypatch, {"gujarat": "state", "gandhinagar": "specific"})

    response = agent.handle(
        ChatMessageRequest(
            user_id="ret",
            message="Plan a trip from Mumbai Airport to Jio Institute on 2026-08-01 at 9 am, and I need a return journey",
        )
    )
    assert response.state.status == "waiting_for_return_origin"

    response = agent.handle(
        ChatMessageRequest(session_id=response.session_id, user_id="ret", message="Same as Jio Institute")
    )
    assert response.state.status == "waiting_for_return_destination"

    # Broad return destination -> pin-point it, mentioning the return journey.
    response = agent.handle(
        ChatMessageRequest(session_id=response.session_id, user_id="ret", message="Gujarat")
    )
    assert "where in Gujarat" in response.message
    assert "return journey" in response.message
    assert response.state.status == "waiting_for_return_destination"

    # Specific place is accepted, pinned independently, and the flow proceeds.
    response = agent.handle(
        ChatMessageRequest(session_id=response.session_id, user_id="ret", message="Gandhinagar")
    )
    assert "where in" not in response.message.lower()
    assert response.state.constraints.return_destination == "Gandhinagar"
    assert response.state.constraints.return_destination_pinned == "Gandhinagar"
    assert response.state.status != "waiting_for_return_destination"


def test_return_journey_slots_collected_one_at_a_time(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    response = agent.handle(
        ChatMessageRequest(
            user_id="chat-return",
            message="Plan a trip from Ahmedabad to Jio Institute tomorrow",
        )
    )
    assert response.state.status == "waiting_for_start_time"

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id, user_id="chat-return", message="9:00 AM"
        )
    )
    assert response.state.status == "waiting_for_return"

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id,
            user_id="chat-return",
            message="Yes, I need a return journey",
        )
    )
    assert response.state.constraints.return_required is True
    assert response.state.status == "waiting_for_return_origin"

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id,
            user_id="chat-return",
            message="Same as Jio Institute",
        )
    )
    assert response.state.constraints.return_origin == "Jio Institute"
    assert response.state.status == "waiting_for_return_destination"

    # The return can end somewhere other than the onward origin.
    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id,
            user_id="chat-return",
            message="Gandhinagar",
        )
    )
    assert response.state.constraints.return_destination == "Gandhinagar"
    assert response.state.status == "waiting_for_return_date"

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id,
            user_id="chat-return",
            message="2026-07-20",
        )
    )
    assert response.state.constraints.return_date == "2026-07-20"
    # The onward start date must not be clobbered by the return date answer.
    assert response.state.constraints.start_date == "tomorrow"
    assert response.state.status == "waiting_for_return_time"

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id, user_id="chat-return", message="6 pm"
        )
    )
    assert response.state.constraints.return_time == "6 pm"
    assert response.state.constraints.start_time == "9:00 am"
    assert response.state.status == "waiting_for_preference_choice"

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id,
            user_id="chat-return",
            message="Use my usual saved preferences",
        )
    )
    assert response.state.status == "choosing_route"
    assert response.state.active_trip_id


def test_first_prompt_with_all_details_skips_to_return_question(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    response = agent.handle(
        ChatMessageRequest(
            user_id="chat-full",
            message="Plan a trip from Ahmedabad to Jio Institute on 2026-08-01 at 9 am",
        )
    )
    constraints = response.state.constraints
    assert constraints.origin == "Ahmedabad"
    assert constraints.destination == "Jio Institute"
    assert constraints.start_date == "2026-08-01"
    assert constraints.start_time == "9 am"
    assert response.state.status == "waiting_for_return"


def test_first_prompt_with_arrival_deadline_fills_start_time(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    response = agent.handle(
        ChatMessageRequest(
            user_id="chat-deadline",
            message="Plan a trip from Koramangala to Whitefield by 6pm",
        )
    )
    constraints = response.state.constraints
    assert constraints.origin == "Koramangala"
    assert constraints.destination == "Whitefield"
    assert constraints.deadline == "6pm"
    # The deadline also satisfies start_time so the bot doesn't re-ask for a
    # time already given, and only the still-missing date is requested next.
    assert constraints.start_time == "6pm"
    assert response.state.status == "waiting_for_start_date"


def test_bare_first_message_captured_as_destination(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    response = agent.handle(
        ChatMessageRequest(user_id="chat-bare-first", message="Pune")
    )
    # A standalone place name before any question has been asked is the
    # traveller naming their destination ("where are you heading today?"),
    # not a value that should be silently dropped. "Pune" alone is a whole
    # city, so it's narrowed once, not asked for again from scratch.
    assert response.state.constraints.destination == "Pune"
    assert response.state.constraints.origin is None
    assert response.state.status == "waiting_for_destination"
    assert "pune" in response.message.lower()

    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id,
            user_id="chat-bare-first",
            message="Just Pune is fine",
        )
    )
    assert response.state.constraints.destination == "Pune"
    assert response.state.status in ("waiting_for_origin", "awaiting_origin_choice")

    # Sharing the device location next must resolve a real origin and must
    # not re-trigger the destination-narrowing question that was already
    # settled by "Just Pune is fine" above.
    response = agent.handle(
        ChatMessageRequest(
            session_id=response.session_id,
            user_id="chat-bare-first",
            message="Use my current location",
            current_lat=23.0225,
            current_lng=72.5714,
        )
    )
    assert response.state.constraints.origin == "Ahmedabad"
    assert response.state.constraints.destination == "Pune"
    assert "where in pune" not in response.message.lower()
    assert response.state.status != "waiting_for_destination"


def test_current_location_after_destination_does_not_reask_destination(tmp_path, monkeypatch):
    agent = make_agent(tmp_path, monkeypatch)
    session_id = "chat-loc-after-dest"
    state = agent.memory.get_or_create(session_id=session_id, user_id="chat-loc-after-dest")
    # Mimic the state left behind after the destination has already been
    # collected (e.g. by the LLM slot-filling wrapper) and the agent is now
    # waiting for the origin.
    state.constraints.destination = "Whitefield"
    state.status = "waiting_for_origin"

    response = agent.handle(
        ChatMessageRequest(
            session_id=session_id,
            user_id="chat-loc-after-dest",
            message="Use my current location",
            current_lat=23.0225,
            current_lng=72.5714,
        )
    )
    # The origin must resolve to the real reverse-geocoded place, never the
    # literal button text, and the already-known destination must not be
    # asked for again.
    assert response.state.constraints.origin == "Ahmedabad"
    assert response.state.constraints.destination == "Whitefield"
    assert response.state.status != "waiting_for_destination"


def test_natural_language_date_is_parsed():
    from datetime import date

    from llm.conversation_agent import ConversationAgent

    base = date(2026, 7, 15)
    assert ConversationAgent._parse_date_expr("20 July", base) == date(2026, 7, 20)
    assert ConversationAgent._parse_date_expr("20th July 2026", base) == date(2026, 7, 20)
    assert ConversationAgent._parse_date_expr("July 20", base) == date(2026, 7, 20)
    assert ConversationAgent._parse_date_expr("20/08/2026", base) == date(2026, 8, 20)
    # A bare month/day already past this year rolls to the next year.
    assert ConversationAgent._parse_date_expr("10 January", base) == date(2027, 1, 10)
    assert ConversationAgent._parse_date_expr("gibberish", base) is None


def test_start_time_resolves_in_client_timezone():
    from datetime import datetime, timezone as tz

    from llm.conversation_agent import ConversationAgent
    from llm.schemas import ConversationState, TravelConstraints

    state = ConversationState(
        session_id="s",
        user_id="u",
        constraints=TravelConstraints(start_date="tomorrow", start_time="9:00 AM"),
    )
    request = ChatMessageRequest(
        user_id="u",
        message="9:00 AM",
        client_time=datetime(2026, 7, 15, 10, 0, tzinfo=tz.utc),
        timezone="Asia/Kolkata",
    )
    resolved = ConversationAgent._resolved_start(state, request)
    # 9 AM on the user's clock (IST), not 9 AM UTC (= 14:30 IST).
    assert resolved is not None
    assert resolved.endswith("+05:30")
    assert "T09:00:00" in resolved
