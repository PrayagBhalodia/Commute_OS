"""Validate dataset manifest license and intended-use declarations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from data_pipeline.scripts.common import ROOT

MANIFEST = ROOT / "data_pipeline" / "manifest" / "dataset_manifest.yaml"
REQUIRED = {
    "name", "source_url", "publisher", "license", "intended_use",
    "commercial_use", "records", "languages", "relevant_fields",
    "download_date", "redistribution_allowed", "attribution_required", "track",
}


def inspect_manifest(path: Path = MANIFEST) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    records = [*(data.get("datasets") or []), *(data.get("rag_sources") or [])]
    errors: list[str] = []
    for item in records:
        missing = REQUIRED - set(item)
        if missing:
            errors.append(f"{item.get('id', 'unknown')}: missing {sorted(missing)}")
        if not item.get("license"):
            errors.append(f"{item.get('id', 'unknown')}: empty license")
        if any(language not in {"english", "hinglish"} for language in item.get("languages", [])):
            errors.append(f"{item.get('id', 'unknown')}: unsupported language")
    return {
        "valid": not errors,
        "entries": len(records),
        "accepted": sum(str(item.get("status", "")).startswith("accepted") for item in records),
        "rejected_or_restricted": sum(not str(item.get("status", "")).startswith("accepted") for item in records),
        "errors": errors,
    }


def main() -> None:
    result = inspect_manifest()
    print(json.dumps(result, indent=2))
    if not result["valid"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
