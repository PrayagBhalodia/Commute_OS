"""Leakage-safe deterministic dataset splitting by scenario group."""

from __future__ import annotations

import hashlib

from datasets.scripts.common import scenario_fingerprint


def split_records(records: list[dict]) -> dict[str, list[dict]]:
    output = {"train": [], "validation": [], "test": []}
    for record in records:
        group = scenario_fingerprint(record)
        bucket = int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) % 10
        split = "train" if bucket < 8 else "validation" if bucket == 8 else "test"
        output[split].append(record)
    return output


def assert_no_group_leakage(splits: dict[str, list[dict]]) -> None:
    groups = {
        name: {scenario_fingerprint(record) for record in records}
        for name, records in splits.items()
    }
    names = list(groups)
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            overlap = groups[left] & groups[right]
            if overlap:
                raise ValueError(f"Scenario leakage between {left} and {right}")


__all__ = ["assert_no_group_leakage", "split_records"]
