"""Exact and conservative near-duplicate removal."""

from __future__ import annotations

from difflib import SequenceMatcher

from data_pipeline.scripts.common import content_fingerprint, normalize_text


def _text(record: dict) -> str:
    return " ".join(
        normalize_text(message.get("content", "")).lower()
        for message in record.get("messages", [])
        if message.get("role") in {"user", "assistant"}
    )


def deduplicate_records(
    records: list[dict], threshold: float = 0.93
) -> tuple[list[dict], int]:
    exact: set[str] = set()
    accepted: list[dict] = []
    signatures: list[str] = []
    removed = 0
    for record in records:
        fingerprint = content_fingerprint(record)
        if fingerprint in exact:
            removed += 1
            continue
        value = _text(record)
        # Compare within the same task only; this is deterministic and avoids
        # turning semantically distinct consent examples into duplicates.
        is_near = any(
            prior.get("task") == record.get("task")
            and SequenceMatcher(None, value, signature).ratio() >= threshold
            for prior, signature in zip(accepted[-300:], signatures[-300:])
        )
        if is_near:
            removed += 1
            continue
        exact.add(fingerprint)
        accepted.append(record)
        signatures.append(value)
    return accepted, removed


__all__ = ["deduplicate_records"]
