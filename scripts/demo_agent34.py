#!/usr/bin/env python3
"""Demo: DMOS Agent 3 (Booking) + Agent 4 (Wallet) downstream flow.

Goal:
  "I have an interview tomorrow at Jio Institute in Navi Mumbai.
   I have one suitcase and need to arrive one hour early.
   I also need a return journey."

Run from repository root:
  python scripts/demo_agent34.py

No LLM, API key, network, or user input required.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure repository root is on sys.path when run as a script.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.agent3_booking import BookingAgent
from agents.agent4_wallet import WalletAgent
from api.schemas import (
    BookingRequest,
    GoalContext,
    ItineraryOption,
    LegOption,
    TransportMode,
)


def _banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main() -> None:
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    wallet_db = str(data_dir / "demo_wallet.db")
    booking_db = str(data_dir / "demo_bookings.db")

    # Fresh demo databases each run
    for path in (wallet_db, booking_db):
        p = Path(path)
        if p.exists():
            p.unlink()

    wallet = WalletAgent(db_path=wallet_db)
    booking = BookingAgent(
        wallet_agent=wallet,
        db_path=booking_db,
        failure_rate=0.0,
        latency_seconds=0.0,
    )

    user_id = "user-yaswa"
    trip_id = "trip-jio-interview-demo"

    # ------------------------------------------------------------------
    # 1. Goal context
    # ------------------------------------------------------------------
    appointment = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = appointment.replace(hour=10, minute=0, second=0, microsecond=0)

    goal = GoalContext(
        goal_statement=(
            "I have an interview tomorrow at Jio Institute in Navi Mumbai. "
            "I have one suitcase and need to arrive one hour early. "
            "I also need a return journey."
        ),
        purpose="interview",
        destination_name="Jio Institute",
        destination_address="Jio Institute, Ulwe, Navi Mumbai, Maharashtra",
        appointment_time=appointment,
        return_required=True,
        luggage_count=1,
        required_buffer_minutes=60,
        metadata={"demo": True, "city_pair": "AMD-BOM"},
    )

    _banner("1. GOAL CONTEXT")
    print(f"  Goal:        {goal.goal_statement}")
    print(f"  Destination: {goal.destination_name}")
    print(f"  Appointment: {goal.appointment_time.isoformat()}")
    print(f"  Luggage:     {goal.luggage_count}")
    print(f"  Buffer:      {goal.required_buffer_minutes} minutes")
    print(f"  Return:      {goal.return_required}")

    # ------------------------------------------------------------------
    # 2. Resolved multi-leg itinerary (as Agent 2 would produce)
    # ------------------------------------------------------------------
    dep_home = appointment - timedelta(hours=6)
    leg_home_airport = LegOption(
        leg_id="leg-1-home-airport",
        mode=TransportMode.CAB,
        operator="Ola",
        origin="Ahmedabad Home",
        destination="Ahmedabad Airport",
        departure=dep_home,
        arrival=dep_home + timedelta(minutes=50),
        price=450.0,
        comfort_score=0.7,
        service_id="CAB-SVC-OLA",
        metadata={"luggage": 1},
    )
    leg_flight = LegOption(
        leg_id="leg-2-flight-amd-bom",
        mode=TransportMode.FLIGHT,
        operator="IndiGo",
        origin="Ahmedabad Airport",
        destination="Mumbai Airport",
        departure=dep_home + timedelta(hours=2),
        arrival=dep_home + timedelta(hours=3, minutes=35),
        price=4200.0,
        comfort_score=0.85,
        service_id="FLT-6E-204",
        metadata={},
    )
    leg_airport_jio = LegOption(
        leg_id="leg-3-airport-jio",
        mode=TransportMode.CAB,
        operator="Uber",
        origin="Mumbai Airport",
        destination="Jio Institute",
        departure=dep_home + timedelta(hours=4),
        arrival=dep_home + timedelta(hours=5, minutes=10),
        price=850.0,
        comfort_score=0.75,
        service_id="CAB-SVC-UBR",
        metadata={},
    )

    legs = [leg_home_airport, leg_flight, leg_airport_jio]
    total_price = sum(leg.price for leg in legs)
    itinerary = ItineraryOption(
        itinerary_id="itin-jio-outbound-v1",
        trip_id=trip_id,
        goal_context=goal,
        legs=legs,
        total_price=total_price,
        total_duration_minutes=310.0,
        score=0.92,
        explanation=(
            "Outbound legs for interview at Jio Institute with 60 min buffer; "
            "return legs would be composed similarly by Agent 2."
        ),
        metadata={"direction": "outbound"},
    )

    _banner("2. RESOLVED ITINERARY (from Journey Composition Agent)")
    for i, leg in enumerate(legs, 1):
        print(
            f"  Leg {i}: [{leg.mode.value}] {leg.operator}: "
            f"{leg.origin} → {leg.destination} | ₹{leg.price:.2f}"
        )
    print(f"  Total estimated: ₹{total_price:.2f}")

    # ------------------------------------------------------------------
    # 3–4. Wallet top-up
    # ------------------------------------------------------------------
    _banner("3. WALLET TOP-UP (Agent 4)")
    state = wallet.topup(
        user_id=user_id,
        amount=10000.0,
        trip_id=trip_id,
        description="Demo wallet top-up INR 10,000",
        idempotency_key=f"demo-topup-{trip_id}",
    )
    print(f"  User:    {state.user_id}")
    print(f"  Balance: ₹{state.balance:.2f} {state.currency}")

    # ------------------------------------------------------------------
    # 5–6. Book outbound legs
    # ------------------------------------------------------------------
    _banner("4. BOOKING (Agent 3) — user confirmed")
    request = BookingRequest(
        trip_id=trip_id,
        user_id=user_id,
        itinerary=itinerary,
        user_confirmed=True,
        idempotency_key=f"demo-book-{trip_id}",
        metadata={"demo": True},
    )
    confirmation = booking.book_itinerary(request)
    print(f"  Trip status:    {confirmation.status}")
    print(f"  All confirmed:  {confirmation.all_confirmed}")
    print(f"  Total charged:  ₹{confirmation.total_charged:.2f}")
    print("  Booking references:")
    for lc in confirmation.leg_confirmations:
        print(
            f"    - {lc.leg_id}: {lc.booking_ref} "
            f"[{lc.status}] ₹{lc.price_charged:.2f} — {lc.message}"
        )

    # ------------------------------------------------------------------
    # 7. Wallet ledger
    # ------------------------------------------------------------------
    _banner("5. WALLET LEDGER")
    for tx in wallet.get_ledger(user_id, trip_id=trip_id):
        print(
            f"  [{tx.type:6}] ₹{tx.amount:8.2f}  "
            f"bal→ ₹{tx.balance_after:8.2f}  | {tx.description}"
        )
    bal = wallet.get_balance(user_id)
    print(f"\n  Current balance: ₹{bal.balance:.2f}")

    # ------------------------------------------------------------------
    # 8–10. Cheaper revised itinerary + reconcile
    # ------------------------------------------------------------------
    revised_total = total_price - 600.0  # e.g. cheaper cab + fare drop
    _banner("6. REROUTE RECONCILIATION (Agent 4)")
    print(f"  Original total: ₹{total_price:.2f}")
    print(f"  Revised total:  ₹{revised_total:.2f} (cheaper alternate)")
    recon = wallet.reconcile(
        trip_id=trip_id,
        user_id=user_id,
        original_total=total_price,
        revised_total=revised_total,
    )
    print(f"  Difference:     ₹{recon.difference:.2f}  (revised - original)")
    print(f"  Action:         {recon.action}")
    print(f"  Message:        {recon.message}")
    print(f"  Balance after:  ₹{recon.wallet_balance_after:.2f}")
    if recon.transaction:
        print(
            f"  Transaction:    {recon.transaction.type} "
            f"₹{recon.transaction.amount:.2f} "
            f"id={recon.transaction.transaction_id}"
        )

    _banner("7. FINAL STATE")
    final = wallet.get_balance(user_id)
    print(f"  Wallet balance: ₹{final.balance:.2f}")
    print(f"  Booking status: {confirmation.status}")
    print(
        "\n  This prototype simulates booking and payments. "
        "It does not perform real transportation bookings "
        "or real financial transactions."
    )
    print("\nDemo complete.")


if __name__ == "__main__":
    main()
