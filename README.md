# DMOS — Daily Mobility Operating System (Commute-OS)

**AI-first, goal-oriented operating system for daily mobility.**

You don't open a cab app, then an airline app, then another. You state a **life goal** in plain language and the OS plans, books (simulated), and pays (simulated) across every transport mode.

> *"I have an interview tomorrow at Jio Institute in Navi Mumbai. One suitcase. Arrive one hour early. Return same evening."*

> ⚠️ **This is a hackathon prototype. Bookings and payments are simulated — no real transport inventory or money movement.**

---

## Major features

- **Goal-oriented input** — natural-language goals (English + Romanized Hinglish), not route forms.
- **Conversational assistant** — multi-turn chat that slot-fills missing origin/destination, explains ranked options, and answers policy questions with citations.
- **5 deterministic agents + orchestrator** — Intent, Journey, Booking, Wallet, Disruption, chained by a chain-of-thought orchestrator (`thought → action → observation → decision → wait_user`).
- **Multi-leg journeys** — cab / flight / train / bus / metro / auto (+ return), ranked and re-scored by learned preferences.
- **Local RAG** — Chroma vector store over a Markdown knowledge base for attributed policy answers (semantic `all-MiniLM` embeddings, deterministic hashing fallback).
- **Worldwide geocoding** — LocationIQ → OpenStreetMap Nominatim → optional Google Maps, with an offline catalog + haversine fallback that always works.
- **Wallet & ledger** — integer paise arithmetic, top-up / debit / refund / reconcile, fully auditable SQLite ledger.
- **Human-in-the-loop safety** — no booking or debit without explicit user consent; failed legs auto-compensate (cancel + refund); all money ops idempotent.
- **Disruption handling** — simulate a disruption → cancel → replan → rebook → reconcile.
- **Preference learning ("Travel DNA")** — learns preferred modes and cheapest/fastest/comfort/eco flags from goals, selections, and feedback.
- **Optional Gemini / OpenAI-compatible LLM** — enriches intent parsing and chat; runs fully offline on deterministic parsers when no key is set.
- **Optional LoRA fine-tuning + data pipeline** — reproducible dataset build and adapter training for English/Hinglish behavior.
- **Two UIs** — polished Next.js web frontend (`frontend/`) plus a Streamlit fallback (`ui/app.py`).
- **FastAPI backend** — typed endpoints with interactive Swagger at `/docs`.

---

## Architecture

```
            ┌─────────────────────────────┐
            │   DMOS Orchestrator (CoT)   │
            │  thought → action → observe │
            └──────────────┬──────────────┘
    ┌──────────┬───────────┼───────────┬──────────┐
    ▼          ▼           ▼           ▼          ▼
 Agent 1    Agent 2     Agent 3     Agent 4    Agent 5
 Intent &   Journey     Booking &   Wallet &   Disruption
 Prefs      Compose     Operators   Payments   & Reroute

 Chat client → ConversationAgent → strict ToolRegistry → Orchestrator
                       └→ optional LLM   └→ local Chroma RAG
```

Agents 3 & 4 (booking + wallet) **never call an LLM** — money and bookings must be deterministic, auditable, and idempotent.

---

## Configuration — API keys

All secrets live in a `.env` file at the repo root. **The `.env` file is gitignored and must never be committed.** Copy the tracked demo template and fill in your own keys:

```bash
cp .env.example .env        # macOS / Linux
copy .env.example .env      # Windows
```

Then edit `.env`. Everything is optional — the app runs fully offline with empty keys:

| Variable | Purpose |
|----------|---------|
| `LOCATIONIQ_API_KEY` | Worldwide geocoding (free tier ~5k/day). Falls back to keyless Nominatim if empty. |
| `GEMINI_API_KEY` | Enables Gemini LLM enrichment for chat/intent. |
| `GOOGLE_MAPS_API_KEY` | Optional live Geocoding + Distance Matrix. |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | OpenAI-compatible conversational provider. |
| `RAG_EMBEDDING_MODEL` / `RAG_ALLOW_MODEL_DOWNLOAD` | Local RAG embedding model and download opt-in. |
| `COMMUTE_*_DB` | SQLite paths for wallet / bookings / profiles (auto-created). |
| `DMOS_UI_MODE` | `local` (in-process) or `api` (call FastAPI) for the Streamlit UI. |

For the frontend, copy `frontend/.env.example` → `frontend/.env.local` and set `NEXT_PUBLIC_API_BASE_URL`.

---

## Quick start

**Prerequisites:** Python 3.11+, Node 18+ (for the frontend).

```bash
# 1. Backend
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                                 # add keys if you have them
python -m rag.ingest                                 # build the local RAG index
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

# 2. Frontend (new terminal)
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

- Web app → http://localhost:3000
- API + Swagger → http://127.0.0.1:8000/docs
- Health → http://127.0.0.1:8000/health

**Streamlit fallback UI:**

```bash
export DMOS_UI_MODE=local && streamlit run ui/app.py   # http://localhost:8501
```

**CLI demos (no UI):**

```bash
python scripts/demo_full_os.py     # Intent → Journey → Book → Feedback → Disruption
pytest -q                          # run the test suite
```

---

## Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/os/plan` | Parse goal → geocode → rank itineraries + chain-of-thought |
| POST | `/os/confirm` | Explicit consent → wallet debit → book |
| POST | `/os/disrupt` | Cancel / rebook / reconcile |
| POST | `/os/feedback` | Learn preferences |
| POST | `/chat/message` | Multi-turn conversational planning |
| POST | `/rag/search` | Search local policy knowledge base |
| GET | `/wallet/{user_id}/balance` | Wallet balance |
| GET | `/places?q=...` | Search / geocode places |

> Plans are held in memory per API process — plan and confirm must hit the **same** running server.

---

## Project layout

```
Commute_OS/
├── agents/           # Agents 1–5 + user_memory (learning)
├── orchestration/    # chain-of-thought orchestrator
├── llm/              # conversational agent, schemas, tool registry
├── rag/              # ingest + Chroma vector store
├── api/              # FastAPI app, chat & OS routes, schemas
├── tools/            # mock cab/flight/transit + maps/places adapters
├── frontend/         # Next.js web app (primary UI)
├── ui/               # Streamlit fallback UI
├── data_pipeline/    # dataset build for fine-tuning
├── finetuning/       # optional LoRA training (needs CUDA + requirements-ml.txt)
├── evaluation/       # chatbot + RAG evaluation
├── scripts/          # CLI demos
├── tests/            # pytest suite
└── docs/             # HLD, RAG workflow, dataset strategy, demo script
```

See `docs/` for detailed design (`HLD.md`), RAG internals (`RAG_WORKFLOW.md`), and the end-to-end demo (`DEMO_SCRIPT.md`).

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError` | Run from repo root with the venv active. |
| Confirm says "unknown trip_id" | Plan and confirm against the same FastAPI process (plans are in-memory). |
| Frontend shows backend offline | Start FastAPI on `127.0.0.1:8000` or fix `NEXT_PUBLIC_API_BASE_URL`. |
| Google Maps not used | Check `GET /health` → `google_maps: true` and key validity. |
| Port 8000 in use | `uvicorn api.main:app --port 8001` and update `DMOS_API_BASE`. |

---

## Disclaimer

Hackathon educational prototype. All bookings, operator references, wallet top-ups, debits, refunds, and reconciliations are **simulated**. No real transport inventory or payment processor is used. The bundled RAG corpus is durable guidance, not live prices, schedules, or advisories.
