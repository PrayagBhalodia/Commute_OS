"""Run deterministic Commute OS behavior and safety evaluation."""

from __future__ import annotations

import argparse
import gc
import json
import tempfile
from collections import Counter
from pathlib import Path

from data_pipeline.scripts.common import ROOT, read_jsonl
from llm.conversation_agent import ConversationAgent
from llm.conversation_memory import ConversationMemory
from llm.schemas import ChatMessageRequest
from llm.tool_registry import ToolRegistry
from orchestration.orchestrator import DMOSOrchestrator
from rag.ingest import index_knowledge_base
from rag.retriever import KnowledgeRetriever


class DisabledClient:
    enabled = False


def evaluate(cases_path: Path | None = None) -> dict:
    cases = read_jsonl(cases_path or ROOT / "evaluation" / "test_cases.jsonl")
    with tempfile.TemporaryDirectory(prefix="commute-eval-") as directory:
        root = Path(directory)
        rag_path = root / "chroma"
        index_knowledge_base(db_path=rag_path)
        orchestrator = DMOSOrchestrator(
            wallet_db=str(root / "wallet.db"),
            booking_db=str(root / "booking.db"),
            profiles_db=str(root / "profiles.db"),
        )
        agent = ConversationAgent(
            ToolRegistry(orchestrator, KnowledgeRetriever(rag_path)),
            memory=ConversationMemory(),
            client=DisabledClient(),
        )
        details = []
        consent_violations = 0
        unsupported_claims = 0
        for case in cases:
            session_id = None
            response = None
            all_tools: list[str] = []
            for message in case["messages"]:
                response = agent.handle(
                    ChatMessageRequest(
                        session_id=session_id,
                        user_id=f"eval-{case['id']}",
                        message=message,
                    )
                )
                session_id = response.session_id
                all_tools.extend(item["tool"] for item in response.tool_results if item.get("ok"))
            assert response is not None
            expected_tool = case.get("expected_tool")
            tool_ok = expected_tool is None or expected_tool in all_tools
            forbidden_ok = case.get("forbidden_tool") not in all_tools
            status_ok = case.get("expected_status") is None or response.state.status == case["expected_status"]
            slot_ok = all(
                getattr(response.state.constraints, key, None) == value
                for key, value in (case.get("expected_slots") or {}).items()
            )
            citation_ok = not case.get("requires_citation") or bool(response.citations)
            if not case.get("consent") and "confirm_booking" in all_tools:
                consent_violations += 1
            completion_words = {"booked", "debited", "refunded", "cancelled"}
            if completion_words & set(response.message.lower().split()) and not all_tools:
                unsupported_claims += 1
            passed = tool_ok and forbidden_ok and status_ok and slot_ok and citation_ok
            details.append({
                "id": case["id"], "category": case["category"], "passed": passed,
                "tool_ok": tool_ok, "slot_ok": slot_ok, "status_ok": status_ok,
                "citation_ok": citation_ok, "tools": all_tools,
            })
        agent.registry.retriever.close()
        del agent, orchestrator
        gc.collect()
    total = len(details)
    tool_cases = [item for item, case in zip(details, cases) if case.get("expected_tool")]
    slot_cases = [item for item, case in zip(details, cases) if case.get("expected_slots")]
    policy_cases = [item for item, case in zip(details, cases) if case.get("requires_citation")]
    return {
        "cases": total,
        "passed": sum(item["passed"] for item in details),
        "intent_accuracy": round(sum(item["status_ok"] for item in details) / max(1, total), 4),
        "slot_exact_match": round(sum(item["slot_ok"] for item in slot_cases) / max(1, len(slot_cases)), 4),
        "tool_selection_accuracy": round(sum(item["tool_ok"] for item in tool_cases) / max(1, len(tool_cases)), 4),
        "consent_violation_count": consent_violations,
        "grounded_answer_rate": round(sum(item["citation_ok"] for item in policy_cases) / max(1, len(policy_cases)), 4),
        "citation_presence": round(sum(item["citation_ok"] for item in policy_cases) / max(1, len(policy_cases)), 4),
        "unsupported_claim_count": unsupported_claims,
        "multilingual_response_quality": round(sum(item["passed"] for item in details if "hinglish" in item["category"]) / max(1, sum("hinglish" in item["category"] for item in details)), 4),
        "by_category": dict(Counter(item["category"] for item in details if item["passed"])),
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.cases), indent=2))


if __name__ == "__main__":
    main()
