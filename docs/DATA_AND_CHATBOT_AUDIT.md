# Data and Chatbot Audit

## Scope

This audit covers the Commute OS repository as of 2026-07-15. The requested
training-data scope is English and Romanized Hindi-English (Hinglish) only.
Hindi in Devanagari and other Indian languages are intentionally excluded from
the generated and downloaded training mix.

## Existing System

- FastAPI exposes planning, booking, wallet, disruption, feedback, place, chat,
  and RAG endpoints.
- Agent 1 extracts intent and preferences; Agent 2 composes and ranks journeys;
  Agent 3 performs simulated bookings; Agent 4 owns the auditable wallet; Agent
  5 handles disruptions. The orchestrator owns cross-agent state transitions.
- The conversational controller stores compact session state, uses an
  allowlisted Pydantic-validated tool registry, and requires explicit booking
  consent.
- Gemini is accessed through an OpenAI-compatible provider abstraction. The
  application remains operational with deterministic fallbacks.
- RAG uses heading-aware Markdown chunks in a persistent Chroma collection.
  Its corpus has ten short, project-authored guidance documents. It does not
  contain live fares, inventory, schedules, traffic, or vehicle positions.
- Places are resolved from a small in-repository India catalog with optional
  Nominatim or Google refinement.

## Gaps

- Existing RAG metadata lacks source URL, publisher/operator, source type,
  license, retrieval date, region, simulation marker, and content hash.
- Filesystem modification time is currently treated as document freshness.
- No normalized instruction dataset, license manifest, deterministic data
  build, leakage-safe split, PII redaction report, or dataset statistics exist.
- English intent extraction is stronger than deterministic Hinglish fallback.
- No repeatable model-training or behavior/retrieval evaluation entry point
  exists.

## Architecture Decision

Two tracks remain separate:

1. RAG contains durable, attributable policy and journey guidance.
2. Fine-tuning data teaches dialogue state, clarification, tool selection,
   consent, disruption, and explanation behavior.

Structured or time-sensitive mobility data belongs in APIs and tools. It is
never converted into durable RAG claims. Fine-tuning is optional and cannot
replace deterministic transaction safeguards.

## Dataset Decision

- Accept Schema-Guided Dialogue travel subsets under CC BY-SA 4.0.
- Accept a small sampled subset of the synthetic Hinglish Everyday
  Conversations dataset under its declared MIT license, with quality filtering.
- Generate project-owned English/Hinglish Commute OS examples for exact tools
  and safety states.
- Exclude AirDialogue from training because CC BY-NC 4.0 is non-commercial.
- Exclude the Akshar Hinglish instruction dataset from training because its
  CC BY-NC-SA 4.0 terms are non-commercial and its source chain includes style
  material whose suitability needs separate review.

## Safety Boundaries

- No private conversations or production identifiers are ingested.
- PII-like emails, phone numbers, payment numbers, and booking references are
  redacted before output.
- Booking examples without explicit consent must resolve to a blocked or
  clarification state, never a successful booking tool call.
- Public source attribution and inherited license requirements are retained per
  record and in the dataset manifest.
