"""Run the complete reproducible English/Hinglish dataset build."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from datasets.scripts.common import INTERIM_DIR, PROCESSED_DIR, write_jsonl
from datasets.scripts.deduplicate import deduplicate_records
from datasets.scripts.download_datasets import run_downloads
from datasets.scripts.filter_travel_dialogues import filter_all
from datasets.scripts.generate_synthetic_travel_data import generate_records
from datasets.scripts.inspect_licenses import inspect_manifest
from datasets.scripts.normalize_dialogues import normalize_records
from datasets.scripts.redact_pii import redact_records
from datasets.scripts.split_dataset import assert_no_group_leakage, split_records
from datasets.scripts.validate_dataset import validate_records

RAG_EVALUATION = [
    {"id": "rag-airport-buffer-en", "language": "english", "query": "How early should I reach the airport?", "expected_categories": ["airport-transfer-guidance", "connection-buffer-guidance"]},
    {"id": "rag-airport-buffer-hi", "language": "hinglish", "query": "Airport kitna early pahuchna chahiye?", "expected_categories": ["airport-transfer-guidance", "connection-buffer-guidance"]},
    {"id": "rag-baggage-en", "language": "english", "query": "What should I check for airline baggage?", "expected_categories": ["baggage-guidance"]},
    {"id": "rag-baggage-hi", "language": "hinglish", "query": "Flight baggage ke rules kya hain?", "expected_categories": ["baggage-guidance"]},
    {"id": "rag-refund-en", "language": "english", "query": "How do cancellation refunds work?", "expected_categories": ["cancellation-refund-guidance"]},
    {"id": "rag-refund-hi", "language": "hinglish", "query": "Cancel karne par refund kaise milega?", "expected_categories": ["cancellation-refund-guidance"]},
    {"id": "rag-access-en", "language": "english", "query": "Can I request wheelchair assistance?", "expected_categories": ["accessibility-guidance"]},
    {"id": "rag-access-hi", "language": "hinglish", "query": "Wheelchair assistance kaise request karun?", "expected_categories": ["accessibility-guidance"]},
]


def _statistics(records: list[dict], splits: dict[str, list[dict]], report: dict, duplicates: int, pii: int) -> dict:
    def counts(field: str) -> dict:
        return dict(Counter(str(record.get(field) or "unknown") for record in records))

    turns = [len(record.get("messages") or []) for record in records]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_records": len(records),
        "split_distribution": {name: len(values) for name, values in splits.items()},
        "language_distribution": counts("language"),
        "task_distribution": counts("task"),
        "intent_distribution": counts("intent"),
        "tool_distribution": dict(Counter((record.get("expected_tool") or {}).get("name", "none") for record in records)),
        "source_distribution": counts("source"),
        "license_distribution": counts("license"),
        "average_turns": round(sum(turns) / max(1, len(turns)), 2),
        "rejected_records": report["rejected"],
        "duplicate_count": duplicates,
        "pii_redactions": pii,
        "synthetic_records": sum(record.get("source") == "synthetic_commute_os" for record in records),
    }


def build(*, max_per_source: int = 5000, dry_run: bool = False, skip_download: bool = False) -> dict:
    manifest = inspect_manifest()
    if not manifest["valid"]:
        raise ValueError(f"Invalid dataset manifest: {manifest['errors']}")
    downloads = [] if skip_download else run_downloads(max_per_source=max_per_source, dry_run=dry_run)
    if dry_run:
        return {
            "status": "dry_run",
            "languages": ["english", "hinglish"],
            "manifest": manifest,
            "downloads": downloads,
            "synthetic_records_planned": len(generate_records(2)),
        }

    synthetic = generate_records(2)
    external = filter_all(max_per_source)
    normalized, normalization_rejected = normalize_records([*synthetic, *external])
    redacted, pii_count = redact_records(normalized)
    deduplicated, duplicate_count = deduplicate_records(redacted)
    valid, validation = validate_records(deduplicated)
    validation["rejected"] += normalization_rejected
    splits = split_records(valid)
    assert_no_group_leakage(splits)

    write_jsonl(INTERIM_DIR / "normalized_all.jsonl", valid)
    write_jsonl(PROCESSED_DIR / "chatbot_train.jsonl", splits["train"])
    write_jsonl(PROCESSED_DIR / "chatbot_validation.jsonl", splits["validation"])
    write_jsonl(PROCESSED_DIR / "chatbot_test.jsonl", splits["test"])
    write_jsonl(PROCESSED_DIR / "intent_slot_train.jsonl", [record for record in splits["train"] if record.get("intent")])
    write_jsonl(PROCESSED_DIR / "tool_call_train.jsonl", [record for record in splits["train"] if record.get("expected_tool")])
    write_jsonl(PROCESSED_DIR / "rag_evaluation.jsonl", RAG_EVALUATION)
    statistics = _statistics(valid, splits, validation, duplicate_count, pii_count)
    (PROCESSED_DIR / "dataset_statistics.json").write_text(json.dumps(statistics, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "built", "downloads": downloads, **statistics}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-source", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()
    print(json.dumps(build(max_per_source=args.max_per_source, dry_run=args.dry_run, skip_download=args.skip_download), indent=2))


if __name__ == "__main__":
    main()
