#!/usr/bin/env python3
"""End-to-end DMOS demo: Agents 1→2→3→4→5 with chain-of-thought.

  python scripts/demo_full_os.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.schemas import (
    ConfirmPlanRequest,
    DisruptionRequest,
    FeedbackRequest,
    PlanRequest,
)
from orchestration.orchestrator import DMOSOrchestrator


def print_cot(steps) -> None:
    print("\n--- Chain of thought ---")
    for s in steps:
        print(f"  [{s.phase:12}] ({s.agent or 'os'}) {s.title}")
        print(f"               {s.detail[:120]}")


def main() -> None:
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    orch = DMOSOrchestrator(
        wallet_db=str(data / "full_demo_wallet.db"),
        booking_db=str(data / "full_demo_bookings.db"),
        profiles_db=str(data / "full_demo_profiles.db"),
    )
    # Fresh-ish wallet
    user = "user-demo"
    orch.wallet.topup(user, 15000.0, trip_id="seed", description="Demo seed")

    print("=" * 72)
    print("DMOS FULL OS DEMO")
    print("=" * 72)

    plan_req = PlanRequest(
        user_id=user,
        goal_text=(
            "I have an interview tomorrow at Jio Institute in Navi Mumbai. "
            "I have one suitcase and need to arrive one hour early. "
            "I also need a return journey."
        ),
        origin="Ahmedabad",
        destination="Jio Institute",
        max_options=3,
    )
    plan = orch.plan(plan_req)
    print(f"\nStatus: {plan.status}")
    print(f"Route: {plan.origin.name} → {plan.destination.name} (~{plan.distance_km:.0f} km)")
    print(f"Message: {plan.message}")
    print_cot(plan.chain_of_thought)

    print("\n--- Ranked itineraries ---")
    for i, it in enumerate(plan.itineraries, 1):
        print(
            f"  {i}. {it.itinerary_id}  ₹{it.total_price:.0f}  "
            f"{it.total_duration_minutes:.0f}min  score={it.score:.2f}  "
            f"legs={len(it.legs)}"
        )

    best = plan.itineraries[0]
    conf = orch.confirm_and_book(
        ConfirmPlanRequest(
            trip_id=plan.trip_id,
            user_id=user,
            itinerary_id=best.itinerary_id,
            user_confirmed=True,
        )
    )
    print(f"\nBooking: {conf.status} — {conf.message}")
    if conf.booking:
        for lc in conf.booking.leg_confirmations:
            print(f"  ref {lc.booking_ref} [{lc.status}] ₹{lc.price_charged:.0f}")
    print(f"Wallet: ₹{conf.wallet_balance:.2f}" if conf.wallet_balance is not None else "")
    print_cot(conf.chain_of_thought)

    # Feedback learning
    prefs = orch.submit_feedback(
        FeedbackRequest(
            user_id=user,
            trip_id=plan.trip_id,
            rating=5,
            comment="Loved the flight option, prefer fastest next time",
            preferred_mode="flight",
            liked=True,
        )
    )
    print(f"\nLearned prefs: modes={prefs.preferred_modes}, fastest={prefs.prefer_fastest}")

    # Disruption
    if conf.booking and conf.booking.all_confirmed:
        disrupt = orch.handle_disruption(
            DisruptionRequest(
                trip_id=plan.trip_id,
                user_id=user,
                reason="traffic_delay",
                severity="medium",
                auto_rebook=True,
            )
        )
        print(f"\nDisruption: {disrupt.status}")
        print(f"  {disrupt.message}")
        print_cot(disrupt.chain_of_thought)

    print("\n" + "=" * 72)
    print("Demo complete. Prototype only — no real bookings or payments.")
    print("=" * 72)


if __name__ == "__main__":
    main()
