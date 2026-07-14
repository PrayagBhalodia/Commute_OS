"""FastAPI surface for the complete DMOS multi-agent OS.

Agents 1–5 + chain-of-thought orchestrator + wallet/booking + maps.

This prototype simulates booking and payments. It does not perform real
transportation bookings or real financial transactions unless you wire live
operator credentials. Google Maps is optional via GOOGLE_MAPS_API_KEY.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from dotenv import load_dotenv

# Load local configuration before importing providers that read environment
# settings while their modules initialize.
load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.chat_routes import build_chat_router
from agents.agent3_booking import (
    BookingConsentRequiredError,
    BookingError,
    UnsupportedOperatorError,
)
from agents.agent4_wallet import (
    InsufficientFundsError,
    InvalidAmountError,
    WalletError,
    WalletTransactionError,
)
from api.auth import router as auth_router
from api.schemas import (
    BookingConfirmation,
    BookingRequest,
    CancelLegResult,
    CancelTripRequest,
    ConfirmPlanRequest,
    ConfirmPlanResponse,
    DisruptionRequest,
    DisruptionResponse,
    FeedbackRequest,
    PlanRequest,
    PlanResponse,
    ReconcileRequest,
    ReconciliationResult,
    TopUpRequest,
    UserPreferences,
    WalletState,
    WalletTransaction,
)
from orchestration.orchestrator import DMOSOrchestrator
from tools.maps_api import geocode, google_maps_enabled, nominatim_enabled, reverse_geocode
from tools.places_india import list_places

# ---------------------------------------------------------------------------
# App + OS wiring
# ---------------------------------------------------------------------------

WALLET_DB = os.environ.get("COMMUTE_WALLET_DB", "data/wallet.db")
BOOKING_DB = os.environ.get("COMMUTE_BOOKING_DB", "data/bookings.db")
PROFILES_DB = os.environ.get("COMMUTE_PROFILES_DB", "data/profiles.db")

orchestrator = DMOSOrchestrator(
    wallet_db=WALLET_DB,
    booking_db=BOOKING_DB,
    profiles_db=PROFILES_DB,
)
wallet_agent = orchestrator.wallet
booking_agent = orchestrator.booking

app = FastAPI(
    title="DMOS — Daily Mobility Operating System",
    description=(
        "AI-first goal-oriented mobility OS. Agents 1–5 with chain-of-thought "
        "orchestration. This prototype simulates booking and payments."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8501",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
chat_router, chat_services = build_chat_router(orchestrator)
app.include_router(chat_router)
app.state.chat_services = chat_services


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "dmos-full-os",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    maps_provider = "google" if google_maps_enabled() else (
        "openstreetmap" if nominatim_enabled() else "offline"
    )
    return {
        "status": "ok",
        "service": "dmos-full-os",
        "agents": ["intent", "journey", "booking", "wallet", "disruption"],
        "google_maps": google_maps_enabled(),
        "maps_provider": maps_provider,
        "nominatim": nominatim_enabled(),
    }


@app.get("/operators/catalog")
def operators_catalog() -> dict[str, list[str]]:
    return booking_agent.get_operator_catalog()


# ---------------------------------------------------------------------------
# Places / Maps
# ---------------------------------------------------------------------------


@app.get("/places")
def places(
    q: Optional[str] = Query(default=None),
    place_type: Optional[str] = Query(default=None),
) -> list[dict[str, Any]]:
    """Search India place catalog (offline) for map/autocomplete."""
    return list_places(query=q, place_type=place_type)


@app.get("/places/geocode")
def places_geocode(q: str = Query(..., min_length=1)) -> dict[str, Any]:
    result = geocode(q)
    if not result:
        raise HTTPException(status_code=404, detail=f"Could not geocode: {q}")
    return result


@app.get("/places/reverse")
def places_reverse(
    lat: float = Query(...),
    lng: float = Query(...),
) -> dict[str, Any]:
    return reverse_geocode(lat, lng)


# ---------------------------------------------------------------------------
# OS orchestration (chain-of-thought)
# ---------------------------------------------------------------------------


@app.post("/os/plan", response_model=PlanResponse)
def os_plan(body: PlanRequest) -> PlanResponse:
    """Agent 1 → Maps → Agent 2. Returns ranked itineraries + CoT trace."""
    return orchestrator.plan(body)


@app.post("/os/confirm", response_model=ConfirmPlanResponse)
def os_confirm(body: ConfirmPlanRequest) -> ConfirmPlanResponse:
    """User consent → Agent 4 (wallet) → Agent 3 (book)."""
    return orchestrator.confirm_and_book(body)


@app.post("/os/disrupt", response_model=DisruptionResponse)
def os_disrupt(body: DisruptionRequest) -> DisruptionResponse:
    """Agent 5 disruption + optional rebook + wallet reconcile."""
    return orchestrator.handle_disruption(body)


@app.post("/os/feedback", response_model=UserPreferences)
def os_feedback(body: FeedbackRequest) -> UserPreferences:
    """Learn from user feedback (preferences update)."""
    return orchestrator.submit_feedback(body)


@app.get("/os/preferences/{user_id}", response_model=UserPreferences)
def os_preferences(user_id: str) -> UserPreferences:
    return orchestrator.get_preferences(user_id)


@app.put("/os/preferences/{user_id}", response_model=UserPreferences)
def os_update_preferences(user_id: str, body: UserPreferences) -> UserPreferences:
    """Directly save a user's default preferences (settings menu)."""
    body.user_id = user_id
    return orchestrator.memory.save_preferences(body)


@app.get("/os/plan/{trip_id}", response_model=PlanResponse)
def os_get_plan(trip_id: str) -> PlanResponse:
    plan = orchestrator.get_plan(trip_id)
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail="Plan not found (plans are in-memory for this prototype session).",
        )
    return plan


# ---------------------------------------------------------------------------
# Wallet (Agent 4)
# ---------------------------------------------------------------------------


@app.post("/wallet/{user_id}/topup", response_model=WalletState)
def wallet_topup(user_id: str, body: TopUpRequest) -> WalletState:
    try:
        return wallet_agent.topup(
            user_id=user_id,
            amount=body.amount,
            trip_id=body.trip_id,
            description=body.description,
            idempotency_key=body.idempotency_key,
        )
    except InvalidAmountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/wallet/{user_id}/balance", response_model=WalletState)
def wallet_balance(user_id: str) -> WalletState:
    return wallet_agent.get_balance(user_id)


@app.get("/wallet/{user_id}/ledger", response_model=list[WalletTransaction])
def wallet_ledger(
    user_id: str, trip_id: Optional[str] = None
) -> list[WalletTransaction]:
    return wallet_agent.get_ledger(user_id=user_id, trip_id=trip_id)


@app.post("/wallet/reconcile", response_model=ReconciliationResult)
def wallet_reconcile(body: ReconcileRequest) -> ReconciliationResult:
    try:
        return wallet_agent.reconcile(
            trip_id=body.trip_id,
            user_id=body.user_id,
            original_total=body.original_total,
            revised_total=body.revised_total,
        )
    except InvalidAmountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Bookings (Agent 3)
# ---------------------------------------------------------------------------


@app.post("/bookings", response_model=BookingConfirmation)
def create_booking(request: BookingRequest) -> BookingConfirmation | JSONResponse:
    try:
        result = booking_agent.book_itinerary(request)
        if result.status == "failed" and result.error and "Insufficient funds" in (
            result.error or ""
        ):
            return JSONResponse(
                status_code=402,
                content=result.model_dump(mode="json"),
            )
        return result
    except BookingConsentRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except UnsupportedOperatorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BookingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except WalletTransactionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/bookings/{trip_id}", response_model=BookingConfirmation)
def get_booking(trip_id: str) -> BookingConfirmation:
    booking = booking_agent.get_booking(trip_id)
    if booking is None:
        raise HTTPException(status_code=404, detail=f"Booking not found: {trip_id}")
    return booking


@app.post(
    "/bookings/{trip_id}/legs/{leg_id}/cancel",
    response_model=CancelLegResult,
)
def cancel_booking_leg(trip_id: str, leg_id: str) -> CancelLegResult:
    try:
        return booking_agent.cancel_leg(trip_id=trip_id, leg_id=leg_id)
    except BookingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/bookings/{trip_id}/cancel", response_model=BookingConfirmation)
def cancel_booking(trip_id: str, body: CancelTripRequest) -> BookingConfirmation:
    """Cancel an entire trip with a required reason.

    Cancels every still-confirmed leg (refunding the wallet for each),
    persists the structured reason on the booking, and feeds it to the
    preference agent. Idempotent — legs already cancelled are skipped.
    """
    if booking_agent.get_booking(trip_id) is None:
        raise HTTPException(status_code=404, detail=f"Booking not found: {trip_id}")
    try:
        return orchestrator.cancel_trip(
            trip_id,
            reason_category=body.reason_category,
            reason_note=body.reason_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BookingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except WalletError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
