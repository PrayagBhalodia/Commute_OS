"""Validate normalized records, tool schemas, slots, and consent safety."""

from __future__ import annotations

from collections import Counter
from typing import Any

from datasets.scripts.common import ChatRecord, validate_record


def validate_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for record in records:
        try:
            value = validate_record(record)
            text = " ".join(message["content"] for message in value["messages"])
            if len(text) < 8:
                raise ValueError("too_short")
            if len(text) > 20000:
                raise ValueError("too_long")
            slots = value.get("slots") or {}
            missing = set(value.get("required_missing_fields") or [])
            for field in missing:
                if slots.get(field) not in {None, ""}:
                    raise ValueError("slot_marked_present_and_missing")
            tool = value.get("expected_tool")
            if tool and tool["name"] == "plan_journey":
                arguments = tool.get("arguments") or {}
                if not arguments.get("goal_text"):
                    raise ValueError("plan_missing_goal")
            accepted.append(value)
        except Exception as exc:  # validation report must retain all failures
            reasons[str(exc).split("\n", 1)[0]] += 1
    return accepted, {
        "accepted": len(accepted),
        "rejected": len(records) - len(accepted),
        "rejection_reasons": dict(reasons),
    }


__all__ = ["validate_records"]
