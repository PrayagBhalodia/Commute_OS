# Local RAG Workflow

## Corpus

Markdown guidance lives in rag/knowledge_base. The corpus covers baggage,
airport transfers, metro and rail rules, cancellation/refund guidance,
accessibility, safety, journey buffers, mode comparison, and advisory handling.
It intentionally excludes live fares, inventory, schedules, traffic, and
service status.

## Ingestion

Run:

~~~powershell
python -m rag.ingest
~~~

The ingester reads Markdown headings, groups text into roughly 400-700 character
chunks with overlap for longer passages, and records source, category, section,
and updated_at. A SHA-256 identity derived from source, section, and content
deduplicates chunks. Chroma upsert makes repeated ingestion idempotent.

## Embeddings

RAG_EMBEDDING_MODEL defaults to all-MiniLM-L6-v2. Set
RAG_USE_SENTENCE_TRANSFORMERS=1 to use a cached model, or set
RAG_ALLOW_MODEL_DOWNLOAD=1 to permit an explicit model download. Otherwise a
private deterministic 384-dimensional feature-hashing embedder keeps ingestion
and retrieval fully offline.

## Retrieval

~~~python
from rag.retriever import search_knowledge

results = search_knowledge(
    "How much airport buffer should I allow?",
    category="journey-buffer-rules",
    top_k=4,
)
~~~

Results include normalized similarity scores and citation metadata. The chat
API returns those citations alongside the answer.

## API

- POST /rag/search searches without changing the index.
- POST /rag/reindex performs an idempotent upsert.

The persistent database path defaults to data/chroma and is excluded from
version control with the rest of runtime data.
