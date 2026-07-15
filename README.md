# DMOS — Daily Mobility Operating System (Commute-OS)

**AI-first, goal-oriented operating system for daily mobility.**

> **This prototype simulates booking and payments. It does not perform real transportation bookings or real financial transactions.**

You do **not** open Ola, then airline apps, then another cab app.  
You state a **life goal**. The OS figures out transportation.

> *“I have an interview tomorrow at Jio Institute in Navi Mumbai. One suitcase. Arrive one hour early. Return same evening.”*

---

## Why this exists

| Mode-oriented apps (today) | Goal-oriented DMOS |
|----------------------------|--------------------|
| You pick airport, cab app, flight, buffer, payments | You pick a **goal** |
| Fragmented multi-app UX | Single multi-agent OS |
| No shared wallet / ledger | Unified wallet + audit trail |
| Manual rebooking on delay | Agent 5 disruption + reconcile |

Hackathon theme: **AI for X — Reimagining Industries through AI-First Operating Systems.**

---

## Architecture (5 agents + orchestrator)

```
                    ┌─────────────────────────────┐
                    │   DMOS Orchestrator (CoT)   │
                    │  thought → action → observe │
                    └──────────────┬──────────────┘
                                   │
     ┌─────────────┬───────────────┼───────────────┬─────────────┐
     ▼             ▼               ▼               ▼             ▼
 Agent 1       Agent 2         Agent 3         Agent 4       Agent 5
 Intent &      Journey         Booking &       Wallet &      Disruption
 Preference    Composition     Operators       Payments      & Reroute
     │             │               │               │             │
  user memory   maps/places    mock cab/flt    SQLite ledger  cancel+
  learning      scoring        mock transit    paise-safe     rebook
```

| Agent | File | Role | LLM required? |
|-------|------|------|----------------|
| 1 Intent | `agents/agent1_intent.py` | Parse goals, merge learned prefs | No (rule-based NLP) |
| 2 Journey | `agents/agent2_journey.py` | Multi-leg compose + score | No |
| 3 Booking | `agents/agent3_booking.py` | Operator adapters, HITL book | No |
| 4 Wallet | `agents/agent4_wallet.py` | Top-up / debit / refund / reconcile | No |
| 5 Disruption | `agents/agent5_disruption.py` | Cancel, replan, rebook, reconcile | No |
| Orchestrator | `orchestration/orchestrator.py` | Chain-of-thought pipeline | No |

**Why Agents 3 & 4 never call an LLM:** money and bookings must be deterministic, auditable, and idempotent.

### Chain of thought

Every `/os/plan`, `/os/confirm`, and `/os/disrupt` returns a `chain_of_thought` list:

| Phase | Meaning |
|-------|---------|
| `thought` | Reasoning about the user goal |
| `action` | Calling an agent or tool |
| `observation` | Result / evidence |
| `decision` | Choice (e.g. top itinerary) |
| `wait_user` | Human-in-the-loop gate |

---

## Features in this prototype

- Natural-language **goal** input (not route input)
- **India place catalog** + map pins (cities, airports, landmarks)
- Origin from catalog, typed text, or **manual lat/lng** (simulates GPS)
- Destination from catalog/map or free text
- Multi-leg itineraries: cab / flight / train (+ return)
- Preference **learning** from ratings, comments, and selected options
- Wallet in **paise** (integer arithmetic) with ledger
- Explicit **user consent** before any booking debit
- **Disruption** simulation → cancel → rebook → reconcile
- Optional **Google Maps** (Geocoding + Distance Matrix) when API key set
- Offline fallback always works (no keys required)
- Bare-minimum **Streamlit UI**
- FastAPI + Swagger at `/docs`

---

## Project layout

```
Commute_OS/
├── README.md
├── requirements.txt
├── .env.example
├── agents/
│   ├── agent1_intent.py
│   ├── agent2_journey.py
│   ├── agent3_booking.py
│   ├── agent4_wallet.py
│   ├── agent5_disruption.py
│   └── user_memory.py
├── orchestration/
│   └── orchestrator.py
├── api/
│   ├── schemas.py
│   └── main.py
├── tools/
│   ├── places_india.py
│   ├── maps_api.py
│   ├── mock_cab_api.py
│   ├── mock_flight_api.py
│   └── mock_transit_api.py
├── ui/
│   ├── app.py                 # Streamlit OS UI
│   └── components/
├── scripts/
│   ├── demo_agent34.py
│   └── demo_full_os.py
├── tests/
└── data/                      # runtime SQLite (gitignored)
```

---

## Prerequisites

- **Python 3.11+**
- Windows / macOS / Linux
- Optional: Google Cloud API key with Geocoding + Distance Matrix enabled

---

## Setup (step by step)

### 1. Open a terminal at the repository root

```bash
cd path/to/Commute_OS
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) Environment variables

```powershell
# Windows
copy .env.example .env
```

```bash
# macOS / Linux
cp .env.example .env
```

Edit `.env` if needed:

| Variable | Default | Purpose |
|----------|---------|---------|
| `COMMUTE_WALLET_DB` | `data/wallet.db` | Wallet SQLite |
| `COMMUTE_BOOKING_DB` | `data/bookings.db` | Bookings SQLite |
| `COMMUTE_PROFILES_DB` | `data/profiles.db` | User prefs / learning |
| `GOOGLE_MAPS_API_KEY` | _(empty)_ | Live maps (optional) |
| `DMOS_UI_MODE` | `local` | `local` or `api` |
| `DMOS_API_BASE` | `http://127.0.0.1:8000` | API URL when UI mode = api |

> SQLite files are created automatically under `data/`. They are gitignored.

### 5. (Optional) Google Maps

1. Create a key in Google Cloud Console  
2. Enable **Geocoding API** and **Distance Matrix API**  
3. Set `GOOGLE_MAPS_API_KEY` in the environment  

Without a key, DMOS uses the offline India catalog + haversine travel model (fully working).

---

## How to run each component

### A. Run unit / integration tests

From repo root (venv active):

```bash
pytest -q
```

Expected: all tests green (Agent 3/4 + full OS pipeline).

---

### B. Run CLI demos (no UI)

**Downstream booking + wallet only:**

```bash
python scripts/demo_agent34.py
```

**Full OS (Intent → Journey → Book → Feedback → Disruption):**

```bash
python scripts/demo_full_os.py
```

You will see ranked itineraries, booking refs, wallet balance, and chain-of-thought steps printed to the terminal.

---

### C. Run the FastAPI backend

From repo root:

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Then open:

| URL | What |
|-----|------|
| http://127.0.0.1:8000/health | Health + maps status |
| http://127.0.0.1:8000/docs | Interactive Swagger UI |
| http://127.0.0.1:8000/places | India places catalog |
| http://127.0.0.1:8000/operators/catalog | Operators |

#### Key OS endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/os/plan` | Agent 1 + maps + Agent 2 → itineraries + CoT |
| POST | `/os/confirm` | User consent → wallet → book |
| POST | `/os/disrupt` | Agent 5 cancel / rebook / reconcile |
| POST | `/os/feedback` | Learn preferences |
| GET | `/os/preferences/{user_id}` | Profile |
| GET | `/places?q=jio` | Search places |
| GET | `/places/geocode?q=Ahmedabad` | Geocode |
| POST | `/wallet/{user_id}/topup` | Top up |
| GET | `/wallet/{user_id}/balance` | Balance |
| POST | `/bookings` | Direct Agent 3 booking |

#### Example: plan a trip

```bash
curl -s -X POST http://127.0.0.1:8000/os/plan ^
  -H "Content-Type: application/json" ^
  -d "{\"user_id\":\"user-demo\",\"goal_text\":\"Interview tomorrow at Jio Institute, one suitcase, return evening\",\"origin\":\"Ahmedabad\",\"destination\":\"Jio Institute\",\"max_options\":3}"
```

(macOS/Linux: use `\` line breaks and single quotes around JSON.)

#### Example: confirm booking

Use `trip_id` and `itinerary_id` from the plan response (**same API process** — plans are held in memory for the prototype):

```bash
curl -s -X POST http://127.0.0.1:8000/os/confirm ^
  -H "Content-Type: application/json" ^
  -d "{\"trip_id\":\"TRIP_ID\",\"user_id\":\"user-demo\",\"itinerary_id\":\"ITIN_ID\",\"user_confirmed\":true}"
```

---

### D. Run the Streamlit UI (recommended for demos)

**Simplest path (in-process orchestrator, no separate API):**

```powershell
# Windows PowerShell
$env:DMOS_UI_MODE="local"
streamlit run ui/app.py
```

```bash
# macOS / Linux
export DMOS_UI_MODE=local
streamlit run ui/app.py
```

Browser opens at http://localhost:8501

**UI flow:**

1. Set **User ID** (sidebar) and **top up** wallet (e.g. ₹10,000)  
2. Enter a **goal** (or pick an example)  
3. Choose **origin / destination** from India catalog (or type names / lat-lng)  
4. Click **Plan my journey** → inspect **chain of thought**  
5. Select an itinerary → check **I confirm booking** → **Confirm & book**  
6. Optionally **Trigger disruption** (Agent 5)  
7. Submit **feedback** so the OS learns preferences  

**UI talking to FastAPI instead:**

Terminal 1:

```bash
uvicorn api.main:app --reload --port 8000
```

Terminal 2:

```powershell
$env:DMOS_UI_MODE="api"
$env:DMOS_API_BASE="http://127.0.0.1:8000"
streamlit run ui/app.py
```

> **Important:** In `api` mode, plan → confirm must hit the **same** running server (plans are in-memory per process).

---

## How learning works

`agents/user_memory.py` stores:

- Preferred / avoided modes  
- Cheapest vs fastest vs comfort vs eco flags  
- Home pin  
- Interaction count + free-text notes from comments  

Signals come from:

1. Phrases in the goal (“cheap”, “fastest”, “eco”)  
2. Which itinerary the user **selects**  
3. Explicit **feedback** (rating, comment, preferred_mode)  

Agent 2 **re-scores** future options using these preferences.

---

## Transport & maps APIs (prototype)

| Capability | Implementation |
|------------|----------------|
| Cab quote/book/cancel | `tools/mock_cab_api.py` (Ola/Uber style) |
| Flight quote/book/cancel | `tools/mock_flight_api.py` |
| Train/bus/metro/auto | `tools/mock_transit_api.py` |
| India places | `tools/places_india.py` |
| Distance / geocode | `tools/maps_api.py` → Google if key else haversine |

Adapters return normalized dicts (`success`, `booking_ref`, `amount`, …) so real partner APIs can replace mocks later without rewriting Agents 3–5.

---

## Human-in-the-loop safeguards

- `user_confirmed=false` → **no booking, no debit**  
- Wallet pre-check before operator calls  
- Debit only after operator success  
- Failed mid-itinerary → compensate (cancel + refund)  
- Idempotent top-up / debit / refund / re-book  

---

## Integration contract (Agent 2 → Agent 3)

```python
from orchestration.orchestrator import DMOSOrchestrator
from api.schemas import PlanRequest, ConfirmPlanRequest

orch = DMOSOrchestrator()
plan = orch.plan(PlanRequest(
    user_id="u1",
    goal_text="Interview at Jio Institute tomorrow",
    origin="Ahmedabad",
    destination="Jio Institute",
))
conf = orch.confirm_and_book(ConfirmPlanRequest(
    trip_id=plan.trip_id,
    user_id="u1",
    itinerary_id=plan.itineraries[0].itinerary_id,
    user_confirmed=True,  # required
))
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: api` | Run commands from **repo root**; venv active |
| Plan OK but confirm “Unknown trip_id” | Same process required; restart and plan again; or use `DMOS_UI_MODE=local` |
| Streamlit map empty | Ensure `pandas` installed (`pip install pandas`) |
| Google maps not used | Check `GET /health` → `google_maps: true` and key validity |
| Tests fail on dirty DBs | Tests use temp dirs; run `pytest -q` from root |
| Port 8000 in use | `uvicorn api.main:app --port 8001` and set `DMOS_API_BASE` |

---

## Future production path

- Live Ola / Uber / airline NDC / IRCTC / RedBus  
- Real UPI / Razorpay wallet top-up  
- LLM-backed Intent (Agent 1) + RAG city knowledge  
- Live traffic / weather tools for Agent 2 & 5  
- Durable plan store (Redis/Postgres) instead of in-memory  
- Mobile client using the same `/os/*` contracts  

---

## Disclaimer

Hackathon educational prototype.

**This prototype simulates booking and payments. It does not perform real transportation bookings or real financial transactions.**

---

## Next.js Frontend

A polished production-style web frontend now lives in `frontend/`. The Streamlit UI remains available as a fallback demo.

### Frontend Architecture

The frontend uses a lightweight MVC-inspired structure:

- `src/models`: TypeScript interfaces and Zod schemas matching the FastAPI/Pydantic contracts.
- `src/services`: typed API clients for journey, wallet, booking, places, preferences, and system health.
- `src/controllers`: React Query hooks coordinating user actions and mutations.
- `src/components`: reusable layout, assistant, journey, wallet, monitoring, and shared UI components.
- `src/app`: Next.js App Router screens.
- `src/store`: small persisted Zustand store for the active prototype trip and selected itinerary.

### Frontend Setup

Terminal 1:

```powershell
cd "C:\Users\VIRAJ\OneDrive\Desktop\commute os\Commute_OS"
python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd "C:\Users\VIRAJ\OneDrive\Desktop\commute os\Commute_OS\frontend"
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

### Environment Variable

Create `frontend/.env.local` from `frontend/.env.example` if needed:

```powershell
copy .env.example .env.local
```

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

### Main UI Routes

| Route | Purpose |
|-------|---------|
| `/` | AI-first home, prompt examples, backend status, wallet summary |
| `/plan` | Natural-language planning and ranked multimodal recommendations |
| `/journey/[tripId]` | Selected journey timeline and leg details |
| `/booking/[tripId]` | Booking review, wallet balance, consent gate |
| `/wallet` | Journey Account, top-up, ledger, refunds and debits |
| `/active` | Live journey status and demo disruption |
| `/preferences` | Travel DNA, autonomy level, feedback learning |
| `/history` | Past and simulated journey states |

### Demo Flow

Use the built-in prompt:

> I have an interview tomorrow at Jio Institute in Navi Mumbai. I am travelling from Ahmedabad with one suitcase. I need to arrive one hour early and return the same evening. Prioritize reliability and time.

Flow:

Home → Load demo scenario → Plan options → Select itinerary → Review booking → Top up wallet if desired → Explicit consent → Confirm complete journey → Active journey → Trigger disruption → Alternative journey → Wallet reconciliation → Feedback.

### Troubleshooting

| Issue | Fix |
|-------|-----|
| Frontend shows backend offline | Start FastAPI on `127.0.0.1:8000` or update `NEXT_PUBLIC_API_BASE_URL`. |
| Confirm says unknown `trip_id` | Plan and confirm against the same running FastAPI process; plans are in-memory for this prototype. |
| PowerShell blocks `npm` | Use `npm.cmd install`, `npm.cmd run dev`, or adjust PowerShell execution policy. |
| Wallet appears empty | Top up in `/wallet` or `/booking/[tripId]`; wallet DB is local SQLite. |

### Simulated Booking and Payment Disclaimer

The frontend is a hackathon prototype client. All bookings, operator references, wallet top-ups, debits, refunds, and reconciliations are simulated through the existing Python backend. No real transport inventory or payment processor is used.

---

## Conversational LLM and Local RAG

DMOS includes a conversational controller above the existing deterministic
five-agent orchestrator. It collects trip constraints over multiple turns,
asks for missing origin or destination, plans journeys, explains ranked
options, answers policy questions with local citations, and coordinates
approved tools. It never replaces deterministic booking, wallet, refund, or
reconciliation logic.

### High-level design

~~~text
Chat client -> ConversationAgent -> strict ToolRegistry -> DMOSOrchestrator
                         |
                         +-> OpenAI-compatible LLM (optional)
                         +-> local Chroma RAG -> Markdown knowledge base
~~~

See docs/HLD.md for the detailed design, docs/RAG_WORKFLOW.md for ingestion and
retrieval, and docs/DEMO_SCRIPT.md for an end-to-end demonstration.

### Setup

~~~powershell
pip install -r requirements.txt
python -m rag.ingest
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
~~~

The application remains functional when LLM_API_KEY is empty. In that mode,
the conversational layer uses deterministic extraction and responses.

| Variable | Default | Purpose |
|----------|---------|---------|
| LLM_API_KEY | empty | Enables the OpenAI-compatible provider |
| LLM_BASE_URL | provider default | Optional compatible API base URL |
| LLM_MODEL | gpt-4.1-mini | Provider model identifier |
| LLM_TEMPERATURE | 0.2 | Provider response temperature |
| RAG_EMBEDDING_MODEL | all-MiniLM-L6-v2 | Local embedding model |
| RAG_DB_PATH | data/chroma | Persistent Chroma database |
| RAG_TOP_K | 4 | Default retrieval count |
| RAG_USE_SENTENCE_TRANSFORMERS | 0 | Enable a cached transformer model |
| RAG_ALLOW_MODEL_DOWNLOAD | 0 | Explicitly permit model download |

### Chat and RAG API

| Method | Path | Purpose |
|--------|------|---------|
| POST | /chat/message | Send a multi-turn chat message |
| GET | /chat/sessions/{session_id} | Read compact session state |
| DELETE | /chat/sessions/{session_id} | Delete conversation memory |
| POST | /rag/search | Search local policy knowledge |
| POST | /rag/reindex | Idempotently index Markdown documents |

Example:

~~~powershell
curl.exe -X POST http://127.0.0.1:8000/chat/message ^
  -H "Content-Type: application/json" ^
  -d "{\"user_id\":\"demo\",\"message\":\"Plan a trip from Ahmedabad to Jio Institute tomorrow\"}"
~~~

### Tool registry and approvals

The allowlisted tools are plan_journey, get_wallet_balance, top_up_wallet,
confirm_booking, trigger_disruption, get_user_preferences, submit_feedback,
search_knowledge, search_places, and get_operator_catalog. Every input is
Pydantic-validated. Unknown tools and extra arguments are rejected.

Autonomy defaults to manual. Smart approval allows proactive suggestions but
still requests approval for consequential actions. Full auto may generate
disruption alternatives automatically, but booking always requires explicit
consent. The API returns safe labels such as intent_parsed,
knowledge_retrieved, journey_planned, waiting_for_consent, and
booking_confirmed; hidden model reasoning is never returned.

### Limitations

Conversation state and planned trip IDs are process-local. The bundled corpus
contains durable guidance, not live prices, availability, schedules, traffic,
or service advisories. An external LLM provider and embedding model download
are optional. All transport bookings and wallet operations remain simulated.

## Dataset And Model Workflow

RAG and fine-tuning are separate. RAG supplies attributed policy and journey
guidance at runtime; it never stores live fares, availability, schedules,
traffic, or locations. Instruction data teaches English/Hinglish conversation,
slot extraction, tool choice, consent, wallet, and disruption behavior.
Optional LoRA changes model behavior, but application startup never requires or
downloads an adapter.

```powershell
pip install -r requirements-data.txt
python -m datasets.scripts.inspect_licenses
python -m datasets.scripts.build_all --dry-run
python -m datasets.scripts.build_all --max-per-source 5000
python -m rag.ingest
python -m rag.evaluation
python -m evaluation.chatbot_eval
```

Licensing decisions are in `docs/DATA_LICENSES.md`. AirDialogue and other
noncommercial sources are excluded from training. Current language scope is
English and Romanized Hinglish only.

Optional adapter training requires CUDA:

```powershell
pip install -r requirements-ml.txt
python -m finetuning.prepare_chat_template
python -m finetuning.train_lora --config finetuning/configs/lora_config.yaml
```

For the hackathon demo, start the API and frontend, send an English or Hinglish
journey request, select a route and per-leg options, review the composed
journey, and explicitly approve booking. Policy questions use cited RAG;
disruptions use deterministic replanning and reconciliation tools.

Known limits: all operator inventory and money movement are simulated, runtime
plans and chat sessions are process-local, source documents are not live service
feeds, and Romanized-language detection is heuristic. See
`docs/DATASET_STRATEGY.md`, `docs/RAG_DATA_PIPELINE.md`, and
`docs/CHATBOT_TRAINING.md` for reproducible workflows.
