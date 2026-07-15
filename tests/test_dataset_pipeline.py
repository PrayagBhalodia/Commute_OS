from pathlib import Path

import pytest

from data_pipeline.scripts.common import ChatRecord, detect_language, redact_text, validate_record
from data_pipeline.scripts.deduplicate import deduplicate_records
from data_pipeline.scripts.generate_synthetic_travel_data import generate_records
from data_pipeline.scripts.inspect_licenses import inspect_manifest
from data_pipeline.scripts.split_dataset import assert_no_group_leakage, split_records
from data_pipeline.scripts.validate_dataset import validate_records


def test_dataset_manifest_has_complete_licenses():
    report = inspect_manifest()
    assert report["valid"] is True
    assert report["entries"] >= 7


def test_synthetic_records_use_only_english_and_hinglish():
    records = generate_records(1)
    assert records
    assert {record["language"] for record in records} == {"english", "hinglish"}
    assert all(record["quality_metadata"]["llm_used"] is False for record in records)


def test_hinglish_normalization_is_preserved():
    value = "Bhai   mujhe kal Mumbai pahuchna hai"
    assert detect_language(value) == "hinglish"
    record = next(item for item in generate_records(1) if item["language"] == "hinglish")
    assert "hai" in " ".join(message["content"].lower() for message in record["messages"])


def test_pii_redaction():
    clean, count = redact_text("Call me at 9876543210 or viraj@example.com")
    assert count == 2
    assert "9876543210" not in clean
    assert "viraj@example.com" not in clean


def test_duplicate_removal():
    record = generate_records(1)[0]
    output, removed = deduplicate_records([record, dict(record)])
    assert len(output) == 1
    assert removed == 1


def test_unknown_tool_is_rejected():
    record = generate_records(1)[0]
    record["expected_tool"] = {"name": "delete_wallet", "arguments": {}}
    with pytest.raises(ValueError):
        validate_record(record)


def test_booking_without_consent_metadata_is_rejected():
    record = next(
        item for item in generate_records(1)
        if (item.get("expected_tool") or {}).get("name") == "confirm_booking"
    )
    record["consent_required"] = False
    with pytest.raises(ValueError):
        validate_record(record)


def test_split_has_no_scenario_leakage():
    splits = split_records(generate_records(2))
    assert_no_group_leakage(splits)
    locations = {}
    for split, records in splits.items():
        for record in records:
            group = record["scenario_group"]
            locations.setdefault(group, set()).add(split)
    assert all(len(values) == 1 for values in locations.values())


def test_dataset_validation_accepts_generated_records():
    records = generate_records(1)
    accepted, report = validate_records(records)
    assert len(accepted) == len(records)
    assert report["rejected"] == 0
