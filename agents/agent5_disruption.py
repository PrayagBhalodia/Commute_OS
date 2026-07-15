"""Agent 5 — Disruption & Rerouting Agent.

Detects/simulates disruptions, cancels affected legs via Agent 3,
recomposes via Agent 2, rebooks with consent, and reconciles wallet via Agent 4.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from agents.agent2_journey import JourneyCompositionAgent
from agents.agent3_booking import BookingAgent, BookingError
from agents.agent4_wallet import WalletAgent
from agents.user_memory import UserMemoryStore
from tools.llm import gemini_enabled, generate_text
from api.schemas import (
    BookingConfirmation,
    BookingRequest,
    DisruptionRequest,
    DisruptionResponse,
    GoalContext,
    ItineraryOption,
    ReconciliationResult,
    ThoughtStep,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DisruptionAgent:
    """Handle mid-trip failures and re-plan remaining journey."""

    def __init__(
        self,
        booking_agent: BookingAgent,
        wallet_agent: WalletAgent,
        journey_agent: Optional[JourneyCompositionAgent] = None,
        memory: Optional[UserMemoryStore] = None,
    ) -> None:
        self.booking = booking_agent
        self.wallet = wallet_agent
        self.journey = journey_agent or JourneyCompositionAgent()
        self.memory = memory or UserMemoryStore()

    def handle(self, request: DisruptionRequest) -> DisruptionResponse:
        """Execute disruption workflow with chain-of-thought steps."""
        thoughts: list[ThoughtStep] = []
        step = 0

        def think(phase: str, title: str, detail: str, agent: str = "agent5", **data: Any) -> None:
            nonlocal step
            step += 1
            thoughts.append(
                ThoughtStep(
                    step_id=step,
                    phase=phase,
                    agent=agent,
                    title=title,
                    detail=detail,
                    data=data,
                    timestamp=_now(),
                )
            )

        think(
            "thought",
            "Assess disruption",
            f"Trip {request.trip_id}: reason={request.reason}, "
            f"severity={request.severity}, leg={request.leg_id}",
        )

        booking = self.booking.get_booking(request.trip_id)
        if booking is None:
            think("observation", "No booking found", "Cannot reroute without an active booking.")
            return DisruptionResponse(
                trip_id=request.trip_id,
                user_id=request.user_id,
                status="failed",
                message=f"No booking found for trip_id={request.trip_id}",
                chain_of_thought=thoughts,
            )

        legs = booking.leg_confirmations
        confirmed = [lc for lc in legs if lc.status == "confirmed"]
        if not confirmed:
            think("observation", "No confirmed legs", "Nothing to cancel or rebook.")
            return DisruptionResponse(
                trip_id=request.trip_id,
                user_id=request.user_id,
                status="no_action",
                message="No confirmed legs to disrupt.",
                chain_of_thought=thoughts,
            )

        # Choose disrupted leg
        target = None
        if request.leg_id:
            target = next((lc for lc in confirmed if lc.leg_id == request.leg_id), None)
        if target is None:
            # Default: disrupt last confirmed leg (often last-mile)
            target = confirmed[-1]

        think(
            "decision",
            "Select disrupted leg",
            f"Disrupting {target.leg_id} ({target.mode}/{target.operator}) "
            f"ref={target.booking_ref}",
            leg_id=target.leg_id,
        )

        original_total = booking.total_charged
        cancelled: list[str] = []
        refund_total = 0.0

        # Cancel disrupted leg (+ optional subsequent legs for high severity)
        to_cancel = [target]
        if request.severity == "high":
            # Cancel this and all following confirmed legs
            idx = next(i for i, lc in enumerate(legs) if lc.leg_id == target.leg_id)
            to_cancel = [lc for lc in legs[idx:] if lc.status == "confirmed"]

        think(
            "action",
            "Cancel affected legs via Agent 3",
            f"Cancelling {len(to_cancel)} leg(s) and refunding wallet.",
            agent="agent3",
        )

        for lc in to_cancel:
            try:
                result = self.booking.cancel_leg(request.trip_id, lc.leg_id)
                cancelled.append(lc.leg_id)
                refund_total += result.refund_amount
                think(
                    "observation",
                    f"Cancelled {lc.leg_id}",
                    f"Refund ₹{result.refund_amount:.2f}; balance ₹{result.wallet_balance_after:.2f}",
                    agent="agent3",
                )
            except BookingError as exc:
                think("observation", f"Cancel failed for {lc.leg_id}", str(exc), agent="agent3")

        revised: Optional[ItineraryOption] = None
        rebooking: Optional[BookingConfirmation] = None
        reconciliation = None

        if request.auto_rebook and cancelled:
            think(
                "thought",
                "Recompose remaining journey",
                "Agent 2 will build a replacement for cancelled segments.",
                agent="agent2",
            )
            prefs = self.memory.get_preferences(request.user_id)
            # Reconstruct a minimal goal from booking metadata / defaults
            goal = GoalContext(
                goal_statement=f"Reroute after disruption: {request.reason}",
                purpose="reroute",
                destination_name=None,
                return_required=False,
                luggage_count=prefs.luggage_default,
                required_buffer_minutes=30,
                metadata={"disruption": request.reason},
            )

            # Infer origin/destination from remaining + cancelled legs
            first_cancelled = to_cancel[0]
            last_cancelled = to_cancel[-1]
            origin_name = first_cancelled.operator  # fallback
            # Better: use mode message — we store origin on legs only in itinerary;
            # use list from booking legs order: origin of cancelled is previous dest
            # From LegBookingConfirmation we don't have origin — use service metadata.
            # Reconstruct from cancelled list positions in full legs.
            full = booking.leg_confirmations
            cidx = next(i for i, x in enumerate(full) if x.leg_id == first_cancelled.leg_id)
            # Origin: if previous leg exists, we don't have dest string; use heuristic
            origin_hint = "Ahmedabad"
            dest_hint = "Jio Institute"
            # Prefer goal from memory events if any
            if booking.leg_confirmations:
                # Parse operator booking messages are weak — use common demo defaults
                # Improved: store itinerary in booking agent goal_context_json
                pass

            # Pull goal_context from DB if present
            origin_hint, dest_hint = self._infer_od_from_booking(request.trip_id, first_cancelled.leg_id)

            new_trip_id = f"{request.trip_id}-reroute-{uuid.uuid4().hex[:6]}"
            o, d, dist, options, jreason = self.journey.compose(
                user_id=request.user_id,
                trip_id=new_trip_id,
                goal=goal,
                preferences=prefs,
                origin_text=origin_hint,
                destination_text=dest_hint,
                max_options=1,
            )
            for r in jreason:
                think("observation", "Journey reasoning", r, agent="agent2")

            if options:
                revised = options[0]
                # Force trip_id on revised
                revised = revised.model_copy(update={"trip_id": new_trip_id})
                think(
                    "decision",
                    "Selected alternate itinerary",
                    f"{revised.itinerary_id} ₹{revised.total_price:.2f} "
                    f"({len(revised.legs)} legs) {o.name} → {d.name}",
                    agent="agent2",
                    itinerary_id=revised.itinerary_id,
                )

                # Optional: Gemini narrates the reroute for the traveller.
                if gemini_enabled():
                    rationale = self._llm_rationale(request, revised, o.name, d.name)
                    if rationale:
                        think("thought", "Reroute rationale (Gemini)", rationale, agent="agent5")

                # Reconcile money: original remaining value vs new
                # After cancel, wallet was refunded; rebook will debit new total
                think(
                    "action",
                    "Rebook alternate via Agent 3",
                    "user_confirmed=True for auto_rebook prototype path "
                    "(production would re-prompt).",
                    agent="agent3",
                )
                try:
                    # Never manufacture funds: if the wallet cannot cover the
                    # replacement, keep the cancellation + refund but do not
                    # rebook — surface the shortfall for an explicit top-up.
                    bal = self.wallet.get_balance(request.user_id)
                    if bal.balance < revised.total_price:
                        shortfall = revised.total_price - bal.balance
                        think(
                            "decision",
                            "Rebook blocked: insufficient funds",
                            f"Replacement costs ₹{revised.total_price:.2f} but "
                            f"wallet has ₹{bal.balance:.2f}. Top up "
                            f"₹{shortfall:.2f} to rebook.",
                            agent="agent4",
                        )
                        reconciliation = ReconciliationResult(
                            trip_id=request.trip_id,
                            user_id=request.user_id,
                            original_total=refund_total,
                            revised_total=revised.total_price,
                            difference=revised.total_price - refund_total,
                            action="top_up_required",
                            wallet_balance_after=bal.balance,
                            transaction=None,
                            message=(
                                f"Replacement journey needs ₹{revised.total_price:.2f} "
                                f"but the wallet has ₹{bal.balance:.2f}. Top up "
                                f"₹{shortfall:.2f} and rebook."
                            ),
                        )
                    else:
                        rebooking = self.booking.book_itinerary(
                            BookingRequest(
                                trip_id=new_trip_id,
                                user_id=request.user_id,
                                itinerary=revised,
                                user_confirmed=True,
                                idempotency_key=f"rebook-{new_trip_id}",
                                metadata={"parent_trip": request.trip_id, "disruption": request.reason},
                            )
                        )
                        think(
                            "observation",
                            "Rebook result",
                            f"status={rebooking.status}, charged=₹{rebooking.total_charged:.2f}",
                            agent="agent3",
                        )

                        # Money already moved for real: cancel_leg refunded the
                        # cancelled legs and book_itinerary debited the new trip.
                        # The reconciliation is an informational summary only —
                        # executing it as a transfer would double-charge.
                        new_total = rebooking.total_charged if rebooking.all_confirmed else 0.0
                        diff = new_total - refund_total
                        bal_after = self.wallet.get_balance(request.user_id)
                        reconciliation = ReconciliationResult(
                            trip_id=request.trip_id,
                            user_id=request.user_id,
                            original_total=refund_total,
                            revised_total=new_total,
                            difference=diff,
                            action="charge_more" if diff > 0 else ("refund" if diff < 0 else "no_action"),
                            wallet_balance_after=bal_after.balance,
                            transaction=None,
                            message=(
                                f"Settled via leg refunds (₹{refund_total:.2f}) and the "
                                f"rebooking debit (₹{new_total:.2f}); net "
                                f"{'charge' if diff >= 0 else 'refund'} ₹{abs(diff):.2f}."
                            ),
                        )
                        think(
                            "observation",
                            "Wallet reconciliation",
                            f"action={reconciliation.action}: {reconciliation.message}",
                            agent="agent4",
                        )
                except Exception as exc:  # noqa: BLE001
                    think("observation", "Rebook failed", str(exc), agent="agent3")

        self.memory.record_event(
            request.user_id,
            "disruption",
            {
                "trip_id": request.trip_id,
                "reason": request.reason,
                "cancelled": cancelled,
                "refund_total": refund_total,
            },
        )

        status = "rerouted" if rebooking and rebooking.all_confirmed else (
            "cancelled_only" if cancelled else "failed"
        )
        msg = (
            f"Disrupted {target.leg_id} ({request.reason}). "
            f"Cancelled {len(cancelled)} leg(s), refunded ₹{refund_total:.2f}."
        )
        if rebooking and rebooking.all_confirmed:
            msg += f" Rebooked trip {rebooking.trip_id} for ₹{rebooking.total_charged:.2f}."
        elif reconciliation is not None and reconciliation.action == "top_up_required":
            msg += f" {reconciliation.message}"

        think("decision", "Disruption handling complete", msg)

        return DisruptionResponse(
            trip_id=request.trip_id,
            user_id=request.user_id,
            disrupted_leg_id=target.leg_id,
            cancelled_legs=cancelled,
            refund_total=refund_total,
            revised_itinerary=revised,
            rebooking=rebooking,
            reconciliation=reconciliation,
            chain_of_thought=thoughts,
            status=status,
            message=msg,
        )

    def _llm_rationale(
        self,
        request: DisruptionRequest,
        revised: ItineraryOption,
        origin_name: str,
        dest_name: str,
    ) -> Optional[str]:
        """One-sentence, reassuring explanation of the reroute, or None."""
        modes = " → ".join(lg.mode.value for lg in revised.legs)
        prompt = (
            "You are a mobility assistant handling a mid-trip disruption. "
            "In ONE short, reassuring sentence (<= 30 words, plain text), tell "
            "the traveller how you are getting them back on track.\n\n"
            f"Disruption: {request.reason} (severity {request.severity}).\n"
            f"New route {origin_name} → {dest_name}: {modes}, "
            f"total ₹{revised.total_price:.0f}, "
            f"{revised.total_duration_minutes:.0f} min."
        )
        return generate_text(prompt, temperature=0.4)

    def _infer_od_from_booking(self, trip_id: str, leg_id: str) -> tuple[str, str]:
        """Best-effort origin/destination from stored goal context JSON."""
        import json
        import sqlite3

        origin, dest = "Ahmedabad", "Jio Institute"
        try:
            with sqlite3.connect(self.booking.db_path) as conn:
                row = conn.execute(
                    "SELECT goal_context_json FROM bookings WHERE trip_id = ?",
                    (trip_id,),
                ).fetchone()
            if row and row[0]:
                gc = json.loads(row[0])
                if gc.get("destination_name"):
                    dest = gc["destination_name"]
                meta = gc.get("metadata") or {}
                if meta.get("origin_hint"):
                    origin = meta["origin_hint"]
        except Exception:
            pass
        return origin, dest
