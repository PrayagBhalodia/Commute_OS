# DMOS Conversational Architecture

## Purpose

The conversational layer sits above the existing deterministic five-agent
mobility operating system. It improves natural-language interaction without
moving booking, wallet, refund, or reconciliation decisions into an LLM.

## Components

~~~text
Client
  |
  v
FastAPI /chat/message
  |
  v
ConversationAgent ---- ConversationMemory
  |        |
  |        +---- OpenAICompatibleClient (optional)
  |
  v
Strict ToolRegistry ---- KnowledgeRetriever ---- Chroma
  |
  v
DMOSOrchestrator
  |
  +---- Agent 1 Intent and Preferences
  +---- Agent 2 Journey Composition
  +---- Agent 3 Deterministic Booking
  +---- Agent 4 Deterministic Wallet
  +---- Agent 5 Disruption and Reconciliation
~~~

ConversationAgent owns compact session state and chooses between deterministic
fallback behavior and an OpenAI-compatible provider. Any provider-generated
tool call is validated against an allowlist and a Pydantic input schema.
Unknown names and extra arguments are rejected.

## Trust Boundaries

- The LLM cannot access SQLite, Python callables, or operator adapters.
- Prices and availability come only from deterministic tools.
- RAG stores durable guidance, never live prices or live availability.
- Booking always requires explicit user_confirmed=true.
- Top-ups require an explicit amount and user instruction.
- Duplicate bookings are checked before the orchestrator is called.
- Chat responses contain safe execution events, not hidden chain-of-thought.

## Availability

With no LLM_API_KEY, the controller extracts common travel constraints, asks
targeted clarification questions, invokes tools, and explains results
deterministically. With a key, an OpenAI-compatible endpoint may provide
additional natural-language control while the same tool and approval boundary
remains in force.

## State

Conversation memory is compact and process-local. It stores the session/user
binding, autonomy level, structured constraints, active trip and itinerary IDs,
status, and a bounded list of turns. Booking and wallet state remain in their
existing SQLite stores. Plans remain process-local in the current prototype.
