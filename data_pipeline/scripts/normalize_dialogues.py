"""Normalize approved external and generated dialogue sources."""

from __future__ import annotations

from data_pipeline.scripts.common import validate_record


def normalize_records(records: list[dict]) -> tuple[list[dict], int]:
    output: list[dict] = []
    rejected = 0
    for record in records:
        try:
            output.append(validate_record(record))
        except (TypeError, ValueError):
            rejected += 1
    return output, rejected


__all__ = ["normalize_records"]
