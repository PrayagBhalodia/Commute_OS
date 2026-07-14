"""Tests for whole-trip cancellation with reason capture.

Covers: the status transition Active/History filtering keys off, the
reason being required (blocking), the reason persisting across a reload,
and the signal reaching the preference agent's feedback pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.agent3_booking import BookingAgent
from agents.agent4_wallet import WalletAgent
from api.schemas import ConfirmPlanRequest, PlanRequest
from orchestration.orchestrator import DMOSOrchestrator

USER = "cancel-user"
GOAL = "I need to get from Pune to Mumbai Airport tomorrow morning with two bags"


@pytest.fixture
def orch(tmp_path: Path) -> DMOSOrchestrator:
    return DMOSOrchestrator(
        wallet_db=str(tmp_path / "w.db"),
        booking_db=str(tmp_path / "b.db"),
        profiles_db=str(tmp_path / "p.db"),
    )


def _book_trip(orch: DMOSOrchestrator) -> str:
    """Plan + confirm a trip; returns its trip_id."""
    orch.wallet.topup(USER, 50000.0, trip_id="seed")
    plan = orch.plan(PlanRequest(user_id=USER, goal_text=GOAL, max_options=1))
    itinerary_id = (
        plan.selected_itinerary_id or plan.itineraries[0].itinerary_id
    )
    conf = orch.confirm_and_book(
        ConfirmPlanRequest(
            trip_id=plan.trip_id,
            user_id=USER,
            itinerary_id=itinerary_id,
            user_confirmed=True,
        )
    )
    assert conf.booking is not None and conf.booking.all_confirmed is True
    return plan.trip_id


def test_cancel_trip_sets_cancelled_status(orch: DMOSOrchestrator) -> None:
    """Status flips to 'cancelled' — the key Active/History filtering uses —
    and every leg is refunded to the wallet."""
    trip_id = _book_trip(orch)
    balance_before = orch.wallet.get_balance(USER).balance
    charged = orch.booking.get_booking(trip_id).total_charged

    updated = orch.cancel_trip(trip_id, reason_category="Change of plans")

    assert updated.status == "cancelled"
    assert all(lc.status == "cancelled" for lc in updated.leg_confirmations)
    assert updated.total_charged == 0.0
    balance_after = orch.wallet.get_balance(USER).balance
    assert balance_after == pytest.approx(balance_before + charged)


def test_cancel_requires_reason(orch: DMOSOrchestrator) -> None:
    """Cancellation is blocked until a non-empty reason category is given."""
    trip_id = _book_trip(orch)

    with pytest.raises(ValueError):
        orch.cancel_trip(trip_id, reason_category="")
    with pytest.raises(ValueError):
        orch.cancel_trip(trip_id, reason_category="   ")

    # Nothing was cancelled by the rejected attempts.
    booking = orch.booking.get_booking(trip_id)
    assert booking.status == "confirmed"
    assert all(lc.status == "confirmed" for lc in booking.leg_confirmations)


def test_reason_persisted_and_survives_reload(
    orch: DMOSOrchestrator, tmp_path: Path
) -> None:
    """Structured reason is stored with the trip and readable after a
    'reload' (fresh agent instance over the same database)."""
    trip_id = _book_trip(orch)
    orch.cancel_trip(
        trip_id,
        reason_category="Found a better price",
        reason_note="IRCTC direct was cheaper",
    )

    stored = orch.booking.get_cancellation_reason(trip_id)
    assert stored is not None
    assert stored["category"] == "Found a better price"
    assert stored["note"] == "IRCTC direct was cheaper"
    assert stored["trip_id"] == trip_id
    assert stored["cancelled_at"]  # ISO timestamp recorded

    # Server-driven state: a brand-new agent over the same DB sees the same
    # cancelled status + reason (what a page reload/refetch would fetch).
    fresh = BookingAgent(
        wallet_agent=WalletAgent(db_path=str(tmp_path / "w.db")),
        db_path=str(tmp_path / "b.db"),
        failure_rate=0.0,
        latency_seconds=0.0,
    )
    reloaded = fresh.get_booking(trip_id)
    assert reloaded is not None and reloaded.status == "cancelled"
    assert fresh.get_cancellation_reason(trip_id) == stored


def test_recancel_is_idempotent_and_keeps_original_reason(
    orch: DMOSOrchestrator,
) -> None:
    trip_id = _book_trip(orch)
    orch.cancel_trip(trip_id, reason_category="Booked by mistake")
    events_after_first = [
        e
        for e in orch.memory.get_events(USER)
        if e["payload"].get("signal") == "trip_cancellation"
    ]

    again = orch.cancel_trip(trip_id, reason_category="Change of plans")

    assert again.status == "cancelled"
    # Original reason is not overwritten, and no duplicate signal is sent.
    assert (
        orch.booking.get_cancellation_reason(trip_id)["category"]
        == "Booked by mistake"
    )
    events_after_second = [
        e
        for e in orch.memory.get_events(USER)
        if e["payload"].get("signal") == "trip_cancellation"
    ]
    assert len(events_after_second) == len(events_after_first) == 1


def test_cancellation_feeds_preference_agent(orch: DMOSOrchestrator) -> None:
    """The structured reason lands in the preference agent's event store and
    runs through the existing keyword-learning pipeline."""
    trip_id = _book_trip(orch)
    before = orch.memory.get_preferences(USER)

    orch.cancel_trip(
        trip_id,
        reason_category="Found a better price",
        reason_note="cheaper bus available",
    )

    events = orch.memory.get_events(USER)
    signal = next(
        e for e in events if e["payload"].get("signal") == "trip_cancellation"
    )
    assert signal["event_type"] == "feedback"
    assert signal["payload"]["category"] == "Found a better price"
    assert signal["payload"]["note"] == "cheaper bus available"
    assert signal["payload"]["trip_id"] == trip_id
    assert signal["payload"]["cancelled_at"]

    after = orch.memory.get_preferences(USER)
    assert after.interaction_count == before.interaction_count + 1
    # "price"/"cheaper" keywords flow through the existing comment learning.
    assert after.prefer_cheapest is True
