"""Extract travel-relevant English and Hinglish dialogues from approved raw data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_pipeline.scripts.common import RAW_DIR, SYSTEM_MESSAGE, detect_language, read_jsonl, validate_record

TRAVEL_TERMS = {
    "airport", "baggage", "booking", "bus", "cab", "cancel", "commute",
    "destination", "flight", "journey", "luggage", "metro", "refund",
    "route", "station", "ticket", "train", "travel", "trip",
    "airport", "bus", "cancel", "flight", "jana", "pahuch", "safar",
    "sasta", "station", "ticket", "train",
}
SGD_SERVICE_PREFIXES = (
    "Flights", "Buses", "Trains", "RideSharing", "RentalCars", "Travel",
    "Hotels", "Weather",
)


def _relevant(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in TRAVEL_TERMS)


def filter_hinglish(limit: int) -> list[dict[str, Any]]:
    rows = read_jsonl(RAW_DIR / "hinglish" / "everyday_conversations.jsonl")
    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        user = str(row.get("input") or row.get("instruction") or "").strip()
        assistant = str(row.get("output") or row.get("response") or "").strip()
        if not user or not assistant or not _relevant(f"{user} {assistant}"):
            continue
        if detect_language(f"{user} {assistant}") != "hinglish":
            continue
        record = {
            "id": f"hinglish-external-{index}",
            "language": "hinglish",
            "domain": "travel",
            "task": "conversation_style",
            "messages": [
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ],
            "intent": "general_travel_conversation",
            "slots": {},
            "required_missing_fields": [],
            "expected_action": "respond",
            "consent_required": False,
            "safe_execution_state": "respond",
            "source": "hinglish_everyday_conversations",
            "license": "MIT",
            "quality_score": 0.65,
            "scenario_group": f"hinglish-external-{index}",
            "quality_metadata": {"synthetic_external": True, "requires_human_review": True},
        }
        try:
            output.append(validate_record(record))
        except ValueError:
            continue
        if len(output) >= limit:
            break
    return output


def _sgd_files() -> list[Path]:
    return sorted(RAW_DIR.glob("schema_guided_dialog/**/train/dialogues_*.json"))


def filter_sgd(limit: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for path in _sgd_files():
        dialogues = json.loads(path.read_text(encoding="utf-8"))
        for dialogue in dialogues:
            services = dialogue.get("services") or []
            if not any(str(service).startswith(SGD_SERVICE_PREFIXES) for service in services):
                continue
            messages = [{"role": "system", "content": SYSTEM_MESSAGE}]
            intents: list[str] = []
            for turn in dialogue.get("turns") or []:
                speaker = str(turn.get("speaker", "")).upper()
                role = "user" if speaker == "USER" else "assistant"
                utterance = str(turn.get("utterance") or "").strip()
                if utterance:
                    messages.append({"role": role, "content": utterance})
                for frame in turn.get("frames") or []:
                    state = frame.get("state") or {}
                    if state.get("active_intent") and state["active_intent"] != "NONE":
                        intents.append(state["active_intent"])
            if len(messages) < 3:
                continue
            identifier = dialogue.get("dialogue_id") or f"{path.stem}-{len(output)}"
            record = {
                "id": f"sgd-{identifier}",
                "language": "english",
                "domain": "travel",
                "task": "dialogue_state_tracking",
                "messages": messages,
                "intent": intents[-1] if intents else "travel_dialogue",
                "slots": {},
                "required_missing_fields": [],
                "expected_action": "follow_annotated_dialogue",
                "consent_required": False,
                "safe_execution_state": "respond",
                "source": "schema_guided_dialog",
                "license": "CC-BY-SA-4.0",
                "quality_score": 0.82,
                "scenario_group": f"sgd-{identifier}",
                "quality_metadata": {"services": services, "active_intents": sorted(set(intents))},
            }
            try:
                output.append(validate_record(record))
            except ValueError:
                continue
            if len(output) >= limit:
                return output
    return output


def filter_all(max_per_source: int) -> list[dict[str, Any]]:
    return [*filter_sgd(max_per_source), *filter_hinglish(max_per_source)]


__all__ = ["filter_all", "filter_hinglish", "filter_sgd"]
