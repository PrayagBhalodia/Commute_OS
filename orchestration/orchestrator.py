"""DMOS multi-agent orchestrator with explicit chain-of-thought tracing.

Pipeline:
  User goal
    → Agent 1 Intent
    → Maps resolve O/D
    → Agent 2 Journey composition
    → (user selects + confirms)
    → Agent 3 Booking + Agent 4 Wallet
    → Agent 5 on disruption

Each phase emits ThoughtStep records (thought / action / observation / decision).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agents.agent1_intent import IntentAgent
from agents.agent2_journey import JourneyCompositionAgent
from agents.agent3_booking import (
    BookingAgent,
    BookingConsentRequiredError,
    BookingError,
)
from agents.agent4_wallet import WalletAgent
from agents.agent5_disruption import DisruptionAgent
from agents.user_memory import UserMemoryStore
from api.schemas import (
    BookingRequest,
    ConfirmPlanRequest,
    ConfirmPlanResponse,
    DisruptionRequest,
    DisruptionResponse,
    FeedbackRequest,
    ItineraryOption,
    PlanRequest,
    PlanResponse,
    ThoughtStep,
    UserPreferences,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DMOSOrchestrator:
    """Coordinates all five agents with a transparent reasoning trace."""

    def __init__(
        self,
        wallet_db: Optional[str] = None,
        booking_db: Optional[str] = None,
        profiles_db: Optional[str] = None,
    ) -> None:
        self.memory = UserMemoryStore(
            db_path=profiles_db
            or os.environ.get("COMMUTE_PROFILES_DB", "data/profiles.db")
        )
        self.wallet = WalletAgent(
            db_path=wallet_db
            or os.environ.get("COMMUTE_WALLET_DB", "data/wallet.db")
        )
        self.booking = BookingAgent(
            wallet_agent=self.wallet,
            db_path=booking_db
            or os.environ.get("COMMUTE_BOOKING_DB", "data/bookings.db"),
            failure_rate=0.0,
            latency_seconds=0.0,
        )
        self.intent = IntentAgent(memory=self.memory)
        self.journey = JourneyCompositionAgent()
        self.disruption = DisruptionAgent(
            booking_agent=self.booking,
            wallet_agent=self.wallet,
            journey_agent=self.journey,
            memory=self.memory,
        )
        # In-memory plan cache for confirm step (prototype)
        self._plans: dict[str, PlanResponse] = {}

    # ------------------------------------------------------------------
    # CoT helper
    # ------------------------------------------------------------------

    def _step(
        self,
        thoughts: list[ThoughtStep],
        phase: str,
        title: str,
        detail: str,
        agent: Optional[str] = None,
        **data: Any,
    ) -> None:
        thoughts.append(
            ThoughtStep(
                step_id=len(thoughts) + 1,
                phase=phase,
                agent=agent,
                title=title,
                detail=detail,
                data=data,
                timestamp=_now(),
            )
        )

    # ------------------------------------------------------------------
    # PLAN
    # ------------------------------------------------------------------

    def plan(self, request: PlanRequest) -> PlanResponse:
        """Run Agent 1 → maps → Agent 2 and return ranked itineraries + CoT."""
        thoughts: list[ThoughtStep] = []
        trip_id = f"trip-{uuid.uuid4().hex[:10]}"

        self._step(
            thoughts,
            "thought",
            "User stated a mobility goal",
            f"Goal: «{request.goal_text}». "
            "User should not need to think in transport modes — we will.",
            agent="orchestrator",
        )

        # Agent 1
        self._step(
            thoughts,
            "action",
            "Invoke Agent 1 — Intent & Preference",
            "Parse natural language, load learned preferences, detect missing fields.",
            agent="agent1",
        )
        intent = self.intent.parse_intent(
            user_id=request.user_id,
            text=request.goal_text,
            origin_hint=request.origin,
            destination_hint=request.destination,
            appointment_time=request.appointment_time,
            return_required=request.return_required,
            luggage_count=request.luggage_count,
            required_buffer_minutes=request.required_buffer_minutes,
        )
        for r in intent.reasoning:
            self._step(thoughts, "observation", "Intent reasoning", r, agent="agent1")

        # Merge explicit coordinates / overrides
        origin_text = request.origin or intent.origin_hint
        dest_text = request.destination or intent.destination_hint
        if request.origin_lat is not None:
            self._step(
                thoughts,
                "observation",
                "Origin from device / map pin",
                f"Coordinates ({request.origin_lat:.4f}, {request.origin_lng})",
                agent="maps",
            )
        if not dest_text and request.destination_lat is None:
            self._step(
                thoughts,
                "wait_user",
                "Destination required",
                "Please select a destination on the India map or type a place name.",
                agent="orchestrator",
            )
            resp = PlanResponse(
                trip_id=trip_id,
                user_id=request.user_id,
                intent=intent,
                origin=None,  # type: ignore[arg-type]
                destination=None,  # type: ignore[arg-type]
                distance_km=0.0,
                itineraries=[],
                chain_of_thought=thoughts,
                status="needs_input",
                message="Destination is required. Pick on map or type a place.",
            )
            # Fix required PlaceInfo — use placeholders for schema validity
            from api.schemas import PlaceInfo

            resp.origin = PlaceInfo(
                place_id="pending",
                name=origin_text or "Unknown",
                address="",
                lat=request.origin_lat or 0.0,
                lng=request.origin_lng or 0.0,
            )
            resp.destination = PlaceInfo(
                place_id="pending",
                name="(select destination)",
                address="",
                lat=0.0,
                lng=0.0,
            )
            self._plans[trip_id] = resp
            return resp

        self._step(
            thoughts,
            "action",
            "Resolve places via Maps tool",
            "Geocode origin/destination (Google Maps if key set, else India catalog).",
            agent="maps",
        )

        # Agent 2
        self._step(
            thoughts,
            "action",
            "Invoke Agent 2 — Journey Composition",
            "Discover modes, build multi-leg options, score with user preferences.",
            agent="agent2",
        )
        o, d, dist, itineraries, jreason = self.journey.compose(
            user_id=request.user_id,
            trip_id=trip_id,
            goal=intent.goal_context,
            preferences=intent.preferences,
            origin_text=origin_text,
            destination_text=dest_text,
            origin_lat=request.origin_lat,
            origin_lng=request.origin_lng,
            destination_lat=request.destination_lat,
            destination_lng=request.destination_lng,
            max_options=request.max_options,
        )
        for r in jreason:
            self._step(thoughts, "observation", "Journey reasoning", r, agent="agent2")

        if not itineraries:
            self._step(
                thoughts,
                "decision",
                "No viable itineraries",
                "Could not compose a route for this O/D pair.",
                agent="agent2",
            )
            resp = PlanResponse(
                trip_id=trip_id,
                user_id=request.user_id,
                intent=intent,
                origin=o,
                destination=d,
                distance_km=dist,
                itineraries=[],
                chain_of_thought=thoughts,
                status="failed",
                message="No itineraries could be composed.",
            )
            self._plans[trip_id] = resp
            return resp

        best = itineraries[0]
        self._step(
            thoughts,
            "decision",
            "Present ranked options to user",
            f"Top option {best.itinerary_id}: ₹{best.total_price:.0f}, "
            f"{best.total_duration_minutes:.0f} min, score={best.score:.2f}. "
            "Awaiting human confirmation before Agent 3 books.",
            agent="orchestrator",
            top_itinerary_id=best.itinerary_id,
        )
        self._step(
            thoughts,
            "wait_user",
            "Human-in-the-loop",
            "Select an itinerary and confirm booking. No money moves without consent.",
            agent="orchestrator",
        )

        resp = PlanResponse(
            trip_id=trip_id,
            user_id=request.user_id,
            intent=intent,
            origin=o,
            destination=d,
            distance_km=dist,
            itineraries=itineraries,
            selected_itinerary_id=best.itinerary_id,
            chain_of_thought=thoughts,
            status="planned",
            message=(
                f"Found {len(itineraries)} option(s) from {o.name} to {d.name} "
                f"(~{dist:.0f} km). Confirm to book."
            ),
        )
        self._plans[trip_id] = resp
        self.memory.record_event(
            request.user_id,
            "plan",
            {
                "trip_id": trip_id,
                "origin": o.name,
                "destination": d.name,
                "options": len(itineraries),
            },
        )
        return resp

    # ------------------------------------------------------------------
    # CONFIRM + BOOK
    # ------------------------------------------------------------------

    def confirm_and_book(self, request: ConfirmPlanRequest) -> ConfirmPlanResponse:
        """User selects itinerary → Agent 4 funds check/topup → Agent 3 book."""
        thoughts: list[ThoughtStep] = []
        plan = self._plans.get(request.trip_id)
        if plan is None:
            return ConfirmPlanResponse(
                trip_id=request.trip_id,
                status="failed",
                message="Unknown trip_id. Call /os/plan first in this server session.",
                chain_of_thought=thoughts,
            )

        self._step(
            thoughts,
            "thought",
            "User selected an itinerary",
            f"itinerary_id={request.itinerary_id}, confirmed={request.user_confirmed}",
            agent="orchestrator",
        )

        if not request.user_confirmed:
            self._step(
                thoughts,
                "decision",
                "Consent denied",
                "Booking aborted — human-in-the-loop safeguard.",
                agent="orchestrator",
            )
            return ConfirmPlanResponse(
                trip_id=request.trip_id,
                status="aborted",
                message="user_confirmed=false; no booking performed.",
                chain_of_thought=thoughts,
            )

        itin = next(
            (i for i in plan.itineraries if i.itinerary_id == request.itinerary_id),
            None,
        )
        if itin is None:
            return ConfirmPlanResponse(
                trip_id=request.trip_id,
                status="failed",
                message=f"Itinerary {request.itinerary_id} not found in plan.",
                chain_of_thought=thoughts,
            )

        # Learn from selection
        modes = list({lg.mode.value for lg in itin.legs})
        cheapest = all(
            itin.total_price <= x.total_price for x in plan.itineraries
        )
        fastest = all(
            itin.total_duration_minutes <= x.total_duration_minutes
            for x in plan.itineraries
        )
        self.memory.learn_from_selection(
            request.user_id,
            {
                "modes": modes,
                "cheapest": cheapest,
                "fastest": fastest,
                "comfort": itin.score > 0.7,
                "itinerary_id": itin.itinerary_id,
            },
        )
        self._step(
            thoughts,
            "observation",
            "Updated user memory",
            f"Learned from selection: modes={modes}, cheapest={cheapest}, fastest={fastest}",
            agent="agent1",
        )

        # Optional top-up
        if request.topup_if_needed and request.topup_if_needed > 0:
            self._step(
                thoughts,
                "action",
                "Wallet top-up (Agent 4)",
                f"Top-up ₹{request.topup_if_needed:.2f}",
                agent="agent4",
            )
            self.wallet.topup(
                request.user_id,
                request.topup_if_needed,
                trip_id=request.trip_id,
                description="Pre-booking top-up",
            )

        bal = self.wallet.get_balance(request.user_id)
        if bal.balance < itin.total_price:
            need = itin.total_price - bal.balance
            self._step(
                thoughts,
                "observation",
                "Insufficient wallet balance",
                f"Need ₹{need:.2f} more (have ₹{bal.balance:.2f}, fare ₹{itin.total_price:.2f}).",
                agent="agent4",
            )
            # Auto top-up shortfall for smoother prototype UX (still explicit in CoT)
            self.wallet.topup(
                request.user_id,
                need + 50,
                trip_id=request.trip_id,
                description="Auto top-up shortfall for confirmed booking",
            )
            self._step(
                thoughts,
                "action",
                "Auto top-up shortfall",
                f"Credited ₹{need + 50:.2f} so booking can proceed after consent.",
                agent="agent4",
            )

        # Ensure itinerary trip_id matches
        itin = itin.model_copy(update={"trip_id": request.trip_id})

        self._step(
            thoughts,
            "action",
            "Invoke Agent 3 — Booking",
            f"Book {len(itin.legs)} leg(s); debit wallet after each operator confirm.",
            agent="agent3",
        )
        try:
            confirmation = self.booking.book_itinerary(
                BookingRequest(
                    trip_id=request.trip_id,
                    user_id=request.user_id,
                    itinerary=itin,
                    user_confirmed=True,
                    idempotency_key=request.idempotency_key
                    or f"os-book-{request.trip_id}-{request.itinerary_id}",
                    metadata={"source": "orchestrator"},
                )
            )
        except (BookingConsentRequiredError, BookingError) as exc:
            self._step(thoughts, "observation", "Booking error", str(exc), agent="agent3")
            return ConfirmPlanResponse(
                trip_id=request.trip_id,
                status="failed",
                message=str(exc),
                chain_of_thought=thoughts,
            )

        bal_after = self.wallet.get_balance(request.user_id)
        self._step(
            thoughts,
            "observation",
            "Booking result",
            f"status={confirmation.status}, charged=₹{confirmation.total_charged:.2f}, "
            f"wallet=₹{bal_after.balance:.2f}",
            agent="agent3",
        )
        self._step(
            thoughts,
            "decision",
            "Trip execution complete",
            "Track trip; Agent 5 can reroute if disruption occurs.",
            agent="orchestrator",
        )

        plan.selected_itinerary_id = request.itinerary_id
        self._plans[request.trip_id] = plan

        return ConfirmPlanResponse(
            trip_id=request.trip_id,
            booking=confirmation,
            wallet_balance=bal_after.balance,
            chain_of_thought=thoughts,
            status=confirmation.status,
            message=(
                "Booking confirmed."
                if confirmation.all_confirmed
                else confirmation.error or "Booking failed."
            ),
        )

    # ------------------------------------------------------------------
    # DISRUPTION
    # ------------------------------------------------------------------

    def handle_disruption(self, request: DisruptionRequest) -> DisruptionResponse:
        self.memory.record_event(
            request.user_id, "disruption_request", request.model_dump(mode="json")
        )
        return self.disruption.handle(request)

    # ------------------------------------------------------------------
    # FEEDBACK / PROFILE
    # ------------------------------------------------------------------

    def submit_feedback(self, request: FeedbackRequest) -> UserPreferences:
        return self.memory.apply_feedback(
            request.user_id,
            rating=request.rating,
            liked=request.liked,
            preferred_mode=request.preferred_mode,
            avoid_mode=request.avoid_mode,
            comment=request.comment,
            selected_itinerary_id=request.selected_itinerary_id,
            metadata=request.metadata,
        )

    def get_preferences(self, user_id: str) -> UserPreferences:
        return self.memory.get_preferences(user_id)

    def get_plan(self, trip_id: str) -> Optional[PlanResponse]:
        return self._plans.get(trip_id)
