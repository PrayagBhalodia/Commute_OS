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

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
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
    BookingConfirmation,
    BookingRequest,
    ConfirmPlanRequest,
    ConfirmPlanResponse,
    DisruptionRequest,
    DisruptionResponse,
    FeedbackRequest,
    ItineraryOption,
    LegOption,
    PlanRequest,
    PlanResponse,
    ThoughtStep,
    UserPreferences,
)
from orchestration.plan_store import PlanStore

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DMOSOrchestrator:
    """Coordinates all five agents with a transparent reasoning trace."""

    def __init__(
        self,
        wallet_db: Optional[str] = None,
        booking_db: Optional[str] = None,
        profiles_db: Optional[str] = None,
        plans_db: Optional[str] = None,
    ) -> None:
        self.memory = UserMemoryStore(
            db_path=profiles_db
            or os.environ.get("COMMUTE_PROFILES_DB", "data/profiles.db")
        )
        self.wallet = WalletAgent(
            db_path=wallet_db
            or os.environ.get("COMMUTE_WALLET_DB", "data/wallet.db")
        )
        booking_path = booking_db or os.environ.get(
            "COMMUTE_BOOKING_DB", "data/bookings.db"
        )
        self.booking = BookingAgent(
            wallet_agent=self.wallet,
            db_path=booking_path,
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
        # SQLite-backed plan store so in-flight plans survive server
        # restarts. Defaults next to the booking DB, keeping tests (which
        # pass tmp-dir paths) isolated from data/.
        self._plans = PlanStore(
            db_path=plans_db
            or os.environ.get("COMMUTE_PLANS_DB")
            or str(Path(booking_path).with_name("plans.db"))
        )

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

    @staticmethod
    def _apply_priority(prefs: UserPreferences, priority: str) -> None:
        """Bias Agent 2's scoring toward one user-chosen priority for this plan
        only. ``prefs`` is a request-scoped object and is not persisted here.
        """
        prefs.prefer_fastest = priority == "time"
        prefs.prefer_cheapest = priority == "cost"
        prefs.prefer_comfort = priority == "comfort"

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

        # Priority-based replanning: the UI sends metadata.priority so switching
        # Time / Cost / Comfort re-scores the same trip. (Eco is ranked on the
        # client since the model no longer tracks emissions.)
        priority = (request.metadata or {}).get("priority")
        if priority in ("time", "cost", "comfort"):
            self._apply_priority(intent.preferences, priority)
            self._step(
                thoughts,
                "decision",
                "Apply user priority",
                f"Re-scoring options to prioritise «{priority}».",
                agent="orchestrator",
            )

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
            # Build valid placeholder PlaceInfo objects up front — PlanResponse
            # requires non-null origin/destination, so passing None here raises
            # a Pydantic ValidationError (500) instead of returning needs_input.
            from api.schemas import PlaceInfo

            placeholder_origin = PlaceInfo(
                place_id="pending",
                name=origin_text or "Unknown",
                address="",
                lat=request.origin_lat or 0.0,
                lng=request.origin_lng or 0.0,
            )
            placeholder_destination = PlaceInfo(
                place_id="pending",
                name="(select destination)",
                address="",
                lat=0.0,
                lng=0.0,
            )
            resp = PlanResponse(
                trip_id=trip_id,
                user_id=request.user_id,
                intent=intent,
                origin=placeholder_origin,
                destination=placeholder_destination,
                distance_km=0.0,
                itineraries=[],
                chain_of_thought=thoughts,
                status="needs_input",
                message=(
                    "I couldn't find a destination in your message. "
                    "Please mention where you need to go."
                ),
            )
            self._plans.put(resp)
            return resp

        # Origin gate: if we genuinely could not determine a starting point,
        # ask for it instead of silently defaulting to a hardcoded city
        # (which produced surprises like "Koramangala → Indiranagar" being
        # planned from Ahmedabad).
        if not origin_text and request.origin_lat is None:
            self._step(
                thoughts,
                "wait_user",
                "Origin required",
                "Please tell me where you're starting from.",
                agent="orchestrator",
            )
            from api.schemas import PlaceInfo

            resp = PlanResponse(
                trip_id=trip_id,
                user_id=request.user_id,
                intent=intent,
                origin=PlaceInfo(
                    place_id="pending",
                    name="(enter starting point)",
                    address="",
                    lat=0.0,
                    lng=0.0,
                ),
                destination=PlaceInfo(
                    place_id="pending",
                    name=dest_text or "(destination)",
                    address="",
                    lat=request.destination_lat or 0.0,
                    lng=request.destination_lng or 0.0,
                ),
                distance_km=0.0,
                itineraries=[],
                chain_of_thought=thoughts,
                status="needs_input",
                message=(
                    f"Got your destination ({dest_text}). Where are you "
                    "starting from? Please mention your origin."
                ),
            )
            self._plans.put(resp)
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
            self._plans.put(resp)
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
        self._plans.put(resp)
        logger.info(
            "Plan %s created for %s: %d option(s) %s -> %s",
            trip_id, request.user_id, len(itineraries), o.name, d.name,
        )
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
            logger.warning(
                "Confirm rejected: unknown trip %s for %s",
                request.trip_id, request.user_id,
            )
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

        # Never manufacture funds: a shortfall fails the confirm with a clear
        # message. Explicit top-ups happen via topup_if_needed or the wallet UI.
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
            logger.warning(
                "Confirm rejected for trip %s: fare %.2f exceeds balance %.2f",
                request.trip_id, itin.total_price, bal.balance,
            )
            return ConfirmPlanResponse(
                trip_id=request.trip_id,
                status="failed",
                wallet_balance=bal.balance,
                chain_of_thought=thoughts,
                message=(
                    f"Insufficient wallet balance: fare ₹{itin.total_price:.2f}, "
                    f"balance ₹{bal.balance:.2f}. Top up ₹{need:.2f} and confirm again."
                ),
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
        self._plans.put(plan)
        logger.info(
            "Booking for trip %s finished with status=%s (charged=%s)",
            request.trip_id, confirmation.status, confirmation.total_charged,
        )

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
        logger.info(
            "Disruption reported on trip %s by %s: %s",
            request.trip_id, request.user_id, request.reason,
        )
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

    def cancel_trip(
        self,
        trip_id: str,
        reason_category: str,
        reason_note: Optional[str] = None,
    ) -> BookingConfirmation:
        """Cancel a whole trip with a required reason.

        Agent 3 cancels the legs (refunding the wallet) and persists the
        structured reason on the booking; the reason is then fed to the
        preference agent through the existing feedback pipeline so future
        planning can learn from it.
        """
        if not (reason_category or "").strip():
            raise ValueError("reason_category is required to cancel a trip")

        before = self.booking.get_booking(trip_id)
        if before is None:
            raise BookingError(f"No booking found for trip_id={trip_id}")
        had_confirmed_legs = any(
            lc.status == "confirmed" for lc in before.leg_confirmations
        )

        updated = self.booking.cancel_trip(
            trip_id,
            reason_category=reason_category,
            reason_note=reason_note,
        )

        # Feed the preference agent only when this call actually cancelled
        # something (idempotent re-cancels should not double-count signals).
        if had_confirmed_legs:
            comment = f"trip cancelled: {reason_category}"
            if reason_note:
                comment += f" — {reason_note}"
            self.memory.apply_feedback(
                updated.user_id,
                comment=comment,
                metadata={
                    "signal": "trip_cancellation",
                    "trip_id": trip_id,
                    "category": reason_category,
                    "note": reason_note or None,
                    "cancelled_at": _now().isoformat(),
                },
            )
        return updated

    def get_preferences(self, user_id: str) -> UserPreferences:
        return self.memory.get_preferences(user_id)

    def get_plan(self, trip_id: str) -> Optional[PlanResponse]:
        return self._plans.get(trip_id)

    def get_leg_options(
        self, trip_id: str, user_id: str, itinerary_id: str
    ) -> list[dict[str, Any]]:
        """Return only alternatives that can occupy each route slot safely."""
        plan = self._plans.get(trip_id)
        if plan is None or plan.user_id != user_id:
            raise ValueError("Active journey plan was not found for this user")
        route = next(
            (item for item in plan.itineraries if item.itinerary_id == itinerary_id),
            None,
        )
        if route is None:
            raise ValueError("Selected route is not part of the active plan")

        groups: list[dict[str, Any]] = []

        def option_payload(leg: LegOption) -> dict[str, Any]:
            payload = leg.model_dump(mode="json")
            premium = leg.metadata.get("variant") == "premium" or leg.comfort_score >= 0.85
            specification = {
                "cab": "XL / AC" if premium else "AC",
                "auto": "Non-AC",
                "flight": "Business" if premium else "Economy",
                "train": "AC Sleeper" if premium else "AC Seater",
                "bus": "AC Sleeper" if premium else "AC Seater",
                "metro": "Standard AC",
            }.get(leg.mode.value, "Standard")
            payload["metadata"] = {**payload.get("metadata", {}), "specification": specification}
            return payload
        for index, base_leg in enumerate(route.legs):
            previous_arrival = route.legs[index - 1].arrival if index else None
            next_departure = (
                route.legs[index + 1].departure
                if index + 1 < len(route.legs)
                else None
            )
            candidates: list[LegOption] = []
            seen: set[tuple[Any, ...]] = set()
            for itinerary in plan.itineraries:
                for leg in itinerary.legs:
                    if leg.origin != base_leg.origin or leg.destination != base_leg.destination:
                        continue
                    if previous_arrival and leg.departure < previous_arrival:
                        continue
                    if next_departure and leg.arrival > next_departure:
                        continue
                    signature = (
                        leg.mode, leg.operator, leg.departure, leg.arrival, leg.price
                    )
                    if signature in seen:
                        continue
                    seen.add(signature)
                    candidates.append(leg)
            candidates.sort(key=lambda leg: (leg.price, leg.arrival, leg.operator))
            if not any(leg.leg_id == base_leg.leg_id for leg in candidates):
                candidates.insert(0, base_leg)
            groups.append(
                {
                    "leg_number": index + 1,
                    "origin": base_leg.origin,
                    "destination": base_leg.destination,
                    "default_leg_id": base_leg.leg_id,
                    "options": [option_payload(leg) for leg in candidates],
                }
            )
        return groups

    def compose_selected_legs(
        self,
        trip_id: str,
        user_id: str,
        route_itinerary_id: str,
        selected_leg_ids: dict[int, str],
    ) -> ItineraryOption:
        """Create a bookable itinerary after validating a per-leg selection."""
        groups = self.get_leg_options(trip_id, user_id, route_itinerary_id)
        chosen: list[LegOption] = []
        for group in groups:
            number = group["leg_number"]
            leg_id = selected_leg_ids.get(number, group["default_leg_id"])
            raw = next(
                (option for option in group["options"] if option["leg_id"] == leg_id),
                None,
            )
            if raw is None:
                raise ValueError(f"Leg {number} option is not compatible with this route")
            chosen.append(LegOption.model_validate(raw))

        for previous, current in zip(chosen, chosen[1:]):
            if previous.destination != current.origin:
                raise ValueError("Selected legs do not form a continuous journey")
            if previous.arrival > current.departure:
                raise ValueError("Selected legs overlap in time")

        # get_leg_options above already validated the plan exists.
        plan = self._plans.get(trip_id)
        assert plan is not None
        route = next(
            item for item in plan.itineraries
            if item.itinerary_id == route_itinerary_id
        )
        composed = ItineraryOption(
            itinerary_id=f"itin-custom-{uuid.uuid4().hex[:10]}",
            trip_id=trip_id,
            goal_context=route.goal_context,
            legs=chosen,
            total_price=round(sum(leg.price for leg in chosen), 2),
            total_duration_minutes=(
                chosen[-1].arrival - chosen[0].departure
            ).total_seconds() / 60,
            score=route.score,
            explanation="User-composed journey from validated compatible leg options.",
            metadata={
                **route.metadata,
                "route_itinerary_id": route_itinerary_id,
                "user_composed": True,
            },
        )
        plan.itineraries = [
            item for item in plan.itineraries
            if not (
                item.metadata.get("user_composed")
                and item.metadata.get("route_itinerary_id") == route_itinerary_id
            )
        ] + [composed]
        plan.selected_itinerary_id = composed.itinerary_id
        return composed
