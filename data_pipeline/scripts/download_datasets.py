"""Download small, manifest-approved public dataset subsets."""

from __future__ import annotations

import argparse
import csv
import io
import json
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

import httpx

from data_pipeline.scripts.common import RAW_DIR, write_jsonl

SGD_ARCHIVE = "https://codeload.github.com/google-research-datasets/dstc8-schema-guided-dialogue/zip/refs/heads/master"
HF_ROWS = "https://datasets-server.huggingface.co/rows"
HINGLISH_CSV = (
    "https://huggingface.co/datasets/Abhishekcr448/"
    "Hinglish-Everyday-Conversations-1M/resolve/main/hinglish_conversations.csv"
)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _get_with_retries(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    attempts: int = 5,
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = httpx.get(
                url, params=params, headers=headers, follow_redirects=True, timeout=60.0
            )
            if response.status_code not in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
                return response
            last_error = httpx.HTTPStatusError(
                f"Retryable status {response.status_code}",
                request=response.request,
                response=response,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
        if attempt < attempts - 1:
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"Dataset service unavailable after {attempts} attempts: {url}") from last_error


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, follow_redirects=True, timeout=90.0) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)


def download_sgd(*, dry_run: bool = False) -> dict:
    destination = RAW_DIR / "schema_guided_dialog"
    if dry_run:
        return {"source": "schema_guided_dialog", "status": "dry_run", "url": SGD_ARCHIVE}
    marker = destination / ".download_complete"
    if marker.exists():
        return {"source": "schema_guided_dialog", "status": "cached"}
    archive = RAW_DIR / "schema_guided_dialog.zip"
    _download(SGD_ARCHIVE, archive)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as value:
        root = destination.resolve()
        for member in value.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError("Unsafe path in SGD archive")
        value.extractall(destination)
    archive.unlink(missing_ok=True)
    marker.write_text("CC-BY-SA-4.0\n", encoding="utf-8")
    return {"source": "schema_guided_dialog", "status": "downloaded"}


def download_hf_rows(
    dataset: str,
    destination: Path,
    *,
    config: str,
    split: str,
    limit: int,
    dry_run: bool = False,
) -> dict:
    if dry_run:
        return {"source": dataset, "status": "dry_run", "records": limit}
    if destination.exists():
        existing = sum(1 for line in destination.open(encoding="utf-8") if line.strip())
        if existing >= limit:
            return {"source": dataset, "status": "cached", "records": existing}
    rows: list[dict] = []
    offset = 0
    while len(rows) < limit:
        length = min(100, limit - len(rows))
        response = _get_with_retries(
            HF_ROWS,
            params={"dataset": dataset, "config": config, "split": split, "offset": offset, "length": length},
        )
        page = response.json().get("rows") or []
        if not page:
            break
        rows.extend(item.get("row", {}) for item in page)
        offset += len(page)
    write_jsonl(destination, rows[:limit])
    return {"source": dataset, "status": "downloaded", "records": len(rows[:limit])}


def download_hinglish_csv_sample(destination: Path, *, limit: int) -> dict:
    response = _get_with_retries(
        HINGLISH_CSV,
        headers={"Range": "bytes=0-4194303"},
    )
    text = response.content.decode("utf-8", errors="ignore")
    # A byte range may end midway through the final CSV row.
    text = text[: text.rfind("\n") + 1]
    rows = [dict(row) for row in csv.DictReader(io.StringIO(text))]
    rows = [row for row in rows if row.get("input") and row.get("output")][:limit]
    write_jsonl(destination, rows)
    return {
        "source": "Abhishekcr448/Hinglish-Everyday-Conversations-1M",
        "status": "downloaded_range_fallback",
        "records": len(rows),
    }


def run_downloads(
    *, max_per_source: int = 5000, dry_run: bool = False, include_evaluation_only: bool = False
) -> list[dict]:
    results = [download_sgd(dry_run=dry_run)]
    hinglish_destination = RAW_DIR / "hinglish" / "everyday_conversations.jsonl"
    try:
        hinglish = download_hf_rows(
            "Abhishekcr448/Hinglish-Everyday-Conversations-1M",
            hinglish_destination,
            config="default",
            split="train",
            limit=max_per_source,
            dry_run=dry_run,
        )
    except RuntimeError:
        if dry_run:
            raise
        hinglish = download_hinglish_csv_sample(
            hinglish_destination, limit=max_per_source
        )
    results.append(hinglish)
    if include_evaluation_only:
        results.append(
            download_hf_rows(
                "google/air_dialogue",
                RAW_DIR / "air_dialogue" / "evaluation_only.jsonl",
                config="air_dialogue_data",
                split="train",
                limit=min(max_per_source, 500),
                dry_run=dry_run,
            )
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-source", type=int, default=5000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--include-evaluation-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_downloads(max_per_source=args.max_per_source, dry_run=args.dry_run, include_evaluation_only=args.include_evaluation_only), indent=2))


if __name__ == "__main__":
    main()
