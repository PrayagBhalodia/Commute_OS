"""Redact common PII patterns from normalized dialogue records."""

from __future__ import annotations

from datasets.scripts.common import redact_record


def redact_records(records: list[dict]) -> tuple[list[dict], int]:
    output, total = [], 0
    for record in records:
        clean, count = redact_record(record)
        output.append(clean)
        total += count
    return output, total


__all__ = ["redact_records"]
