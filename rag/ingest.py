"""Idempotently index Markdown policy documents into local Chroma."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from rag.schemas import IndexStats, KnowledgeChunk
from rag.vector_store import ChromaVectorStore

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge_base"


def _category(path: Path) -> str:
    return path.stem.replace("_", "-")


def parse_frontmatter(text: str) -> tuple[dict[str, str | bool], str]:
    """Parse the deliberately simple YAML front matter used by RAG documents."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    metadata: dict[str, str | bool] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        clean = value.strip().strip('"').strip("'")
        metadata[key.strip()] = clean.lower() == "true" if clean.lower() in {"true", "false"} else clean
    return metadata, parts[2].lstrip()


def chunk_markdown(
    text: str,
    *,
    source: str,
    category: str,
    updated_at: str,
    metadata: dict[str, str | bool] | None = None,
    target_size: int = 550,
    overlap: int = 100,
) -> list[KnowledgeChunk]:
    metadata = metadata or {}
    headings: list[tuple[str, str]] = []
    section = "Overview"
    buffer: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            if buffer:
                headings.append((section, "\n".join(buffer).strip()))
                buffer = []
            section = line.lstrip("#").strip() or "Overview"
        elif line:
            buffer.append(line)
    if buffer:
        headings.append((section, "\n".join(buffer).strip()))

    grouped: list[tuple[str, str]] = []
    pending_sections: list[str] = []
    pending_bodies: list[str] = []
    for section_name, body in headings:
        pending_sections.append(section_name)
        pending_bodies.append(body)
        if len("\n".join(pending_bodies)) >= 400:
            grouped.append((" / ".join(pending_sections), "\n".join(pending_bodies)))
            pending_sections, pending_bodies = [], []
    if pending_bodies:
        if grouped and len("\n".join(pending_bodies)) < 300:
            old_section, old_body = grouped.pop()
            grouped.append(
                (
                    f"{old_section} / {' / '.join(pending_sections)}",
                    f"{old_body}\n{' '.join(pending_bodies)}",
                )
            )
        else:
            grouped.append((" / ".join(pending_sections), "\n".join(pending_bodies)))

    chunks: list[KnowledgeChunk] = []
    for section_name, body in grouped:
        if not body:
            continue
        start = 0
        while start < len(body):
            end = min(len(body), start + target_size)
            if end < len(body):
                boundary = max(
                    body.rfind(". ", start, end),
                    body.rfind("\n", start, end),
                    body.rfind(" ", start, end),
                )
                if boundary > start + 300:
                    end = boundary + 1
            piece = body[start:end].strip()
            if piece:
                identity = f"{source}|{section_name}|{piece}"
                chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                content_hash = hashlib.sha256(piece.encode("utf-8")).hexdigest()
                chunks.append(
                    KnowledgeChunk(
                        chunk_id=chunk_id,
                        text=piece,
                        source=source,
                        category=category,
                        section=section_name,
                        updated_at=updated_at,
                        title=str(metadata.get("title", "")),
                        region=str(metadata.get("region", "India")),
                        operator=str(metadata.get("operator", "")),
                        source_url=str(metadata.get("source_url", "")),
                        source_type=str(metadata.get("source_type", "project-authored")),
                        license=str(metadata.get("license", "project-generated")),
                        retrieved_at=str(metadata.get("retrieved_at", updated_at)),
                        is_simulated=bool(metadata.get("is_simulated", False)),
                        content_hash=content_hash,
                    )
                )
            if end >= len(body):
                break
            start = max(start + 1, end - overlap)
    return chunks


def index_knowledge_base(
    *,
    db_path: str | Path | None = None,
    knowledge_dir: str | Path | None = None,
) -> IndexStats:
    root = Path(knowledge_dir) if knowledge_dir else KNOWLEDGE_DIR
    paths = sorted(root.rglob("*.md"))
    chunks: list[KnowledgeChunk] = []
    for path in paths:
        stat = path.stat()
        fallback_updated_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        metadata, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        updated_at = str(metadata.get("updated_at") or fallback_updated_at)
        chunks.extend(
            chunk_markdown(
                body,
                source=path.name,
                category=str(metadata.get("category") or _category(path)),
                updated_at=updated_at,
                metadata=metadata,
            )
        )
    store = ChromaVectorStore(db_path=db_path)
    added, existing = store.upsert(chunks)
    return IndexStats(
        documents=len(paths),
        chunks=len(chunks),
        added=added,
        existing=existing,
        indexed_at=datetime.now(timezone.utc),
    )


def main() -> None:
    stats = index_knowledge_base()
    print(
        f"Indexed {stats.chunks} chunks from {stats.documents} documents "
        f"({stats.added} new, {stats.existing} existing)."
    )


if __name__ == "__main__":
    main()
