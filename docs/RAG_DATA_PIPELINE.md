# RAG Data Pipeline

Knowledge documents live under `rag/knowledge_base/india` and
`rag/knowledge_base/simulated`. Every document identifies its title, category,
region, operator, source URL, source type, license, update date, retrieval date,
and simulated status.

The ingester recursively reads Markdown, parses front matter, splits on
headings into roughly 400-700 character chunks with overlap, and assigns stable
SHA-256 chunk IDs and content hashes. Chroma upsert makes repeated ingestion
idempotent. Offline feature-hash embeddings are the default; transformer model
downloads require explicit environment opt-in.

```powershell
python -m rag.ingest
python -m rag.evaluation
```

Policy answers return source metadata and citations. Project-authored guidance
avoids unsupported operator-specific claims. Simulated advisories are clearly
marked and must never be presented as live service status.
