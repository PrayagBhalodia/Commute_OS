from pathlib import Path

from llm.schemas import ExecutionTraceEntry
from llm.tool_registry import ToolRegistry
from orchestration.orchestrator import DMOSOrchestrator
from rag.ingest import KNOWLEDGE_DIR, index_knowledge_base
from rag.retriever import KnowledgeRetriever


def make_registry(tmp_path: Path, monkeypatch) -> ToolRegistry:
    monkeypatch.setenv("RAG_FORCE_HASH_EMBEDDINGS", "1")
    rag_path = tmp_path / "chroma"
    index_knowledge_base(db_path=rag_path, knowledge_dir=KNOWLEDGE_DIR)
    orchestrator = DMOSOrchestrator(
        wallet_db=str(tmp_path / "wallet.db"),
        booking_db=str(tmp_path / "booking.db"),
        profiles_db=str(tmp_path / "profiles.db"),
    )
    return ToolRegistry(orchestrator, KnowledgeRetriever(rag_path))


def test_unknown_tools_cannot_run(tmp_path, monkeypatch):
    registry = make_registry(tmp_path, monkeypatch)
    trace: list[ExecutionTraceEntry] = []
    result = registry.execute(
        "run_arbitrary_python",
        {"code": "print('unsafe')"},
        trace=trace,
    )

    assert result["ok"] is False
    assert result["error"] == "unknown_tool"
    assert trace[0].status == "blocked"


def test_booking_requires_explicit_consent(tmp_path, monkeypatch):
    registry = make_registry(tmp_path, monkeypatch)
    result = registry.execute(
        "confirm_booking",
        {
            "trip_id": "trip-1",
            "itinerary_id": "itin-1",
            "user_id": "u1",
            "user_confirmed": False,
        },
    )

    assert result["ok"] is False
    assert result["error"] == "validation_error"


def test_duplicate_booking_is_prevented(tmp_path, monkeypatch):
    registry = make_registry(tmp_path, monkeypatch)
    user_id = "duplicate-user"
    plan = registry.execute(
        "plan_journey",
        {
            "user_id": user_id,
            "goal_text": "Travel from Ahmedabad to Jio Institute tomorrow",
            "origin": "Ahmedabad",
            "destination": "Jio Institute",
        },
    )
    itinerary_id = plan["data"]["itineraries"][0]["itinerary_id"]
    trip_id = plan["data"]["trip_id"]
    registry.execute(
        "top_up_wallet",
        {
            "user_id": user_id,
            "amount": 100000,
            "trip_id": trip_id,
            "idempotency_key": "fund-once",
        },
    )
    payload = {
        "user_id": user_id,
        "trip_id": trip_id,
        "itinerary_id": itinerary_id,
        "user_confirmed": True,
        "idempotency_key": "book-once",
    }

    first = registry.execute("confirm_booking", payload)
    second = registry.execute("confirm_booking", payload)

    assert first["ok"] and first["data"]["status"] == "confirmed"
    assert second["ok"] and second["data"]["status"] == "duplicate_blocked"


def test_wallet_topup_idempotency_remains_deterministic(tmp_path, monkeypatch):
    registry = make_registry(tmp_path, monkeypatch)
    payload = {
        "user_id": "wallet-user",
        "amount": 125.25,
        "trip_id": "wallet",
        "idempotency_key": "same-topup",
    }
    registry.execute("top_up_wallet", payload)
    registry.execute("top_up_wallet", payload)
    balance = registry.execute(
        "get_wallet_balance", {"user_id": "wallet-user"}
    )

    assert balance["data"]["balance"] == 125.25
