# Commute OS Frontend Implementation Notes

## Backend Contracts Inspected

- `GET /health`: returns `status`, `service`, `agents`, `google_maps`.
- `GET /places`: optional `q`, `place_type`, returns `PlaceInfo[]`-like catalog rows.
- `GET /places/geocode`: query `q`, returns a resolved place or 404.
- `GET /operators/catalog`: returns mode-to-operator arrays.
- `POST /os/plan`: accepts `PlanRequest` with `user_id`, `goal_text`, O/D hints, appointment, return, luggage, buffer, `max_options`; returns `PlanResponse`.
- `POST /os/confirm`: accepts `ConfirmPlanRequest` with `trip_id`, `user_id`, `itinerary_id`, `user_confirmed`, optional top-up/idempotency; returns `ConfirmPlanResponse`.
- `POST /os/disrupt`: accepts `DisruptionRequest`; returns cancellation, reroute, rebooking, reconciliation, and trace.
- `POST /os/feedback`: accepts `FeedbackRequest`; returns `UserPreferences`.
- `GET /os/preferences/{user_id}`: returns `UserPreferences`.
- `POST /wallet/{user_id}/topup`: accepts `TopUpRequest`; returns `WalletState`.
- `GET /wallet/{user_id}/balance`: returns `WalletState`.
- `POST /bookings`: accepts direct `BookingRequest`; returns `BookingConfirmation`.

## Architecture

The frontend follows an MVC-inspired shape:

- Models: TypeScript interfaces and Zod schemas in `src/models`.
- Views: App Router routes and presentational components.
- Controllers: React Query hooks in `src/controllers`.
- Services: typed API wrappers in `src/services`.
- State: React Query for server state, Zustand persistence for the current prototype trip.

## Product Notes

The UI labels backend `chain_of_thought` as an `Execution Trace` with safe operational stages. It does not expose hidden reasoning. Booking and payment actions are explicitly marked as simulated.

## Backend Limitations Found

- Plans are stored in process memory, so `/os/confirm` must hit the same running FastAPI process that created `/os/plan`.
- `/os/confirm` auto-tops up wallet shortfalls for demo continuity after explicit consent.
- `/os/disrupt` infers reroute origin/destination best-effort from stored goal context, with demo fallbacks.
- Wallet ledger is available at `/wallet/{user_id}/ledger` even though it was not in the required endpoint list.
