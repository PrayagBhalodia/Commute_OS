"""The wallet must never manufacture funds or double-move money.

Regression tests for:
- disruption rebooking silently topping up the wallet to force an
  unaffordable replacement through (reported: 40k wallet, 35k booking,
  disruption rebooks a 45k replacement and confirms);
- reconcile() re-moving a price difference that per-leg refunds and the
  rebooking debit had already settled;
- confirm_and_book auto-crediting shortfalls;
- crashed booking attempts leaving orphaned wallet debits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.schemas import (
    BookingConfirmation,
    BookingRequest,
    ConfirmPlanRequest,
    DisruptionRequest,
    PlanRequest,
)
from orchestration.orchestrator import DMOSOrchestrator


@pytest.fixture
def orch(tmp_path: Path) -> DMOSOrchestrator:
    return DMOSOrchestrator(
        wallet_db=str(tmp_path / "w.db"),
        booking_db=str(tmp_path / "b.db"),
        profiles_db=str(tmp_path / "p.db"),
    )


def _book_trip(orch: DMOSOrchestrator, user_id: str = "u1") -> str:
    plan = orch.plan(
        PlanRequest(
            user_id=user_id,
            goal_text="Interview at Jio Institute from Ahmedabad",
            origin="Ahmedabad",
            destination="Jio Institute",
            max_options=2,
        )
    )
    conf = orch.confirm_and_book(
        ConfirmPlanRequest(
            trip_id=plan.trip_id,
            user_id=user_id,
            itinerary_id=plan.itineraries[0].itinerary_id,
            user_confirmed=True,
        )
    )
    assert conf.status == "confirmed"
    return plan.trip_id


def _topups(orch: DMOSOrchestrator, user_id: str) -> list:
    return [tx for tx in orch.wallet.get_ledger(user_id) if tx.type == "topup"]


def test_disruption_never_tops_up_wallet(orch: DMOSOrchestrator) -> None:
    orch.wallet.topup("u1", 50000.0, trip_id="seed")
    trip_id = _book_trip(orch)

    # Drain the wallet so no replacement journey is affordable.
    balance = orch.wallet.get_balance("u1").balance
    if balance > 1:
        orch.wallet.debit("u1", balance - 1, trip_id="drain", description="drain")
    topups_before = len(_topups(orch, "u1"))

    disrupt = orch.handle_disruption(
        DisruptionRequest(
            trip_id=trip_id,
            user_id="u1",
            reason="traffic_delay",
            severity="medium",
            auto_rebook=True,
        )
    )

    # The cancellation and its refund stand, but nothing was rebooked and,
    # critically, no money was created out of thin air.
    assert len(_topups(orch, "u1")) == topups_before
    assert disrupt.rebooking is None
    assert disrupt.status == "cancelled_only"
    assert disrupt.reconciliation is not None
    assert disrupt.reconciliation.action == "top_up_required"
    assert "Top up" in disrupt.reconciliation.message


def test_disruption_rebooking_moves_money_exactly_once(orch: DMOSOrchestrator) -> None:
    orch.wallet.topup("u1", 100000.0, trip_id="seed")
    trip_id = _book_trip(orch)

    balance_before = orch.wallet.get_balance("u1").balance
    disrupt = orch.handle_disruption(
        DisruptionRequest(
            trip_id=trip_id,
            user_id="u1",
            reason="traffic_delay",
            severity="medium",
            auto_rebook=True,
        )
    )
    assert disrupt.status == "rerouted"
    assert disrupt.rebooking is not None and disrupt.rebooking.all_confirmed

    # Wallet math: refunds for cancelled legs in, rebooking debit out — and
    # nothing else. The old reconcile() used to move the difference again.
    expected = balance_before + disrupt.refund_total - disrupt.rebooking.total_charged
    assert orch.wallet.get_balance("u1").balance == pytest.approx(expected, abs=0.01)
    assert not any(
        "Reroute reconciliation" in tx.description
        for tx in orch.wallet.get_ledger("u1")
    )
    assert len(_topups(orch, "u1")) == 1  # only the seed


def test_confirm_fails_on_shortfall_instead_of_auto_topup(orch: DMOSOrchestrator) -> None:
    orch.wallet.topup("u1", 50.0, trip_id="seed")
    plan = orch.plan(
        PlanRequest(
            user_id="u1",
            goal_text="Interview at Jio Institute from Ahmedabad",
            origin="Ahmedabad",
            destination="Jio Institute",
            max_options=2,
        )
    )
    conf = orch.confirm_and_book(
        ConfirmPlanRequest(
            trip_id=plan.trip_id,
            user_id="u1",
            itinerary_id=plan.itineraries[0].itinerary_id,
            user_confirmed=True,
        )
    )
    assert conf.status == "failed"
    assert "Top up" in conf.message
    assert conf.booking is None
    assert len(_topups(orch, "u1")) == 1  # only the seed
    assert orch.wallet.get_balance("u1").balance == pytest.approx(50.0)


def test_crashed_booking_attempt_refunds_orphaned_debits(orch: DMOSOrchestrator) -> None:
    from datetime import datetime, timezone

    orch.wallet.topup("u1", 50000.0, trip_id="seed")
    plan = orch.plan(
        PlanRequest(
            user_id="u1",
            goal_text="Interview at Jio Institute from Ahmedabad",
            origin="Ahmedabad",
            destination="Jio Institute",
            max_options=2,
        )
    )
    itinerary = plan.itineraries[0]

    # Simulate a crash mid-booking: the in_progress row was written and one
    # leg was debited, but the outcome was never persisted.
    orch.booking._persist_full_booking(
        BookingConfirmation(
            trip_id=plan.trip_id,
            user_id="u1",
            itinerary_id=itinerary.itinerary_id,
            status="in_progress",
            leg_confirmations=[],
            all_confirmed=False,
            total_charged=0.0,
            failed_legs=[],
            error=None,
            created_at=datetime.now(timezone.utc),
        ),
        None,
        None,
    )
    orch.wallet.debit(
        "u1", 1234.0, trip_id=plan.trip_id, description="Booking debit leg crash-sim"
    )
    balance_after_crash = orch.wallet.get_balance("u1").balance

    booking = orch.booking.book_itinerary(
        BookingRequest(
            trip_id=plan.trip_id,
            user_id="u1",
            itinerary=itinerary,
            user_confirmed=True,
            idempotency_key=f"retry-{plan.trip_id}",
            metadata={},
        )
    )
    assert booking.status == "confirmed"
    # The orphaned 1234 came back before the fresh attempt debited the fare.
    expected = balance_after_crash + 1234.0 - booking.total_charged
    assert orch.wallet.get_balance("u1").balance == pytest.approx(expected, abs=0.01)
