"""Shared contracts and safe text utilities for dataset preparation."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data_pipeline" / "raw"
INTERIM_DIR = ROOT / "data_pipeline" / "interim"
PROCESSED_DIR = ROOT / "data_pipeline" / "processed"
SYSTEM_MESSAGE = "You are Commute OS, an Indian journey-orchestration assistant."

ALLOWED_TOOLS = {
    "plan_journey",
    "get_wallet_balance",
    "top_up_wallet",
    "confirm_booking",
    "get_leg_options",
    "compose_journey",
    "trigger_disruption",
    "get_user_preferences",
    "submit_feedback",
    "search_knowledge",
    "search_places",
    "get_operator_catalog",
}

HINGLISH_MARKERS = {
    "aap", "abhi", "acha", "batao", "bhai", "chahiye", "chalenge",
    "dekho", "dikhao", "ghar", "hai", "hain", "jaldi", "jana", "kar",
    "karo", "karna", "kal", "kya", "liye", "mera", "mere", "mujhe",
    "nahi", "paise", "pahuch", "pahuchna", "sabka", "sabse", "sasta",
    "tak", "thoda", "waapas", "wala", "wali", "ya", "zyada",
}


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1, max_length=8000)


class ExpectedTool(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def known_tool(self):
        if self.name not in ALLOWED_TOOLS:
            raise ValueError(f"Unknown Commute OS tool: {self.name}")
        return self


class ChatRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=3)
    language: Literal["english", "hinglish"]
    domain: str = "travel"
    task: str
    messages: list[Message] = Field(min_length=1)
    intent: str | None = None
    slots: dict[str, Any] = Field(default_factory=dict)
    required_missing_fields: list[str] = Field(default_factory=list)
    expected_action: str
    expected_tool: ExpectedTool | None = None
    consent_required: bool = False
    safe_execution_state: str = "respond"
    source: str
    license: str
    quality_score: float = Field(default=0.8, ge=0.0, le=1.0)
    scenario_group: str | None = None
    quality_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def safety_rules(self):
        if self.language not in {"english", "hinglish"}:
            raise ValueError("Only English and Hinglish records are allowed")
        combined = " ".join(message.content for message in self.messages)
        if re.search(r"[\u0900-\u097f]", combined):
            raise ValueError("Devanagari is outside this dataset build scope")
        if self.expected_tool and self.expected_tool.name == "confirm_booking":
            if not self.consent_required:
                raise ValueError("Booking examples must declare consent_required")
            if self.safe_execution_state not in {"waiting_for_consent", "confirmed"}:
                raise ValueError("Booking example has an unsafe execution state")
        return self


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.replace("\u200b", " ").replace("\ufeff", " ")
    return re.sub(r"\s+", " ", value).strip()


def detect_language(value: str) -> Literal["english", "hinglish"]:
    words = set(re.findall(r"[a-z]+", normalize_text(value).lower()))
    return "hinglish" if len(words & HINGLISH_MARKERS) >= 2 else "english"


PII_PATTERNS = [
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[EMAIL]"),
    (re.compile(r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{9}(?!\d)"), "[PHONE]"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[PAYMENT_NUMBER]"),
    (re.compile(r"\b(?:PNR|booking(?: ref(?:erence)?)?)\s*[:#-]?\s*[A-Z0-9]{6,12}\b", re.I), "[BOOKING_REFERENCE]"),
]


def redact_text(value: str) -> tuple[str, int]:
    output = normalize_text(value)
    count = 0
    for pattern, replacement in PII_PATTERNS:
        output, replacements = pattern.subn(replacement, output)
        count += replacements
    return output, count


def redact_record(record: dict[str, Any]) -> tuple[dict[str, Any], int]:
    clean = json.loads(json.dumps(record))
    count = 0
    for message in clean.get("messages", []):
        message["content"], found = redact_text(message.get("content", ""))
        count += found
    return clean, count


def content_fingerprint(record: dict[str, Any]) -> str:
    content = "|".join(
        normalize_text(message.get("content", "")).lower()
        for message in record.get("messages", [])
        if message.get("role") in {"user", "assistant"}
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def scenario_fingerprint(record: dict[str, Any]) -> str:
    explicit = record.get("scenario_group")
    if explicit:
        return str(explicit)
    slots = record.get("slots") or {}
    signature = {
        "task": record.get("task"),
        "intent": record.get("intent"),
        "origin": slots.get("origin"),
        "destination": slots.get("destination"),
        "expected_action": record.get("expected_action"),
    }
    return hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:20]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    output: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                output.append(json.loads(line))
    return output


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(json.dumps(record))
    for message in normalized.get("messages", []):
        message["content"] = normalize_text(message.get("content", ""))
    value = ChatRecord.model_validate(normalized)
    return value.model_dump(mode="json", exclude_none=True)
