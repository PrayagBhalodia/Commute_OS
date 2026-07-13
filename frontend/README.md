# Commute OS Frontend

Next.js App Router frontend for the Commute OS hackathon prototype.

## Windows Setup

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

Open http://localhost:3000.

## Environment

Copy `.env.example` to `.env.local` if you need to change the API URL.

```powershell
copy .env.example .env.local
```

Default:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Routes

- `/`: AI-first home and demo launcher
- `/plan`: journey planning and ranked recommendations
- `/journey/[tripId]`: selected journey timeline
- `/booking/[tripId]`: consent and booking review
- `/wallet`: Journey Account and ledger
- `/active`: live journey and disruption demo
- `/preferences`: Travel DNA and feedback
- `/history`: simulated journey history

## Scripts

```powershell
npm run dev
npm run lint
npm run typecheck
npm run build
```

Bookings and wallet movements are simulated. No real transport booking or payment is performed.
