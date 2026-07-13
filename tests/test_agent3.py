"""Tests for Agent 3 — Booking & Operator Integration Agent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agents.agent3_booking import (
    BookingAgent,
    BookingConsentRequiredError,
    UnsupportedOperatorError,
)
from agents.agent4_wallet import WalletAgent
from api.schemas import (
    BookingRequest,
    GoalContext,
    ItineraryOption,
    LegOption,
    TransportMode,
)
from tests.conftest import make_leg


def test_operator_catalog_contains_expected_modes(
    booking_agent: BookingAgent,
) -> None:
    catalog = booking_agent.get_operator_catalog()
    for mode in ("cab", "auto", "flight", "train", "bus", "metro"):
        assert mode in catalog
        assert isinstance(catalog[mode], list)
        assert len(catalog[mode]) >= 1
    assert "Ola" in catalog["cab"]
    assert "IndiGo" in catalog["flight"]
    assert "IRCTC" in catalog["train"]


def test_successful_one_leg_cab_booking(
    booking_agent: BookingAgent, wallet: WalletAgent, single_cab_leg: LegOption
) -> None:
    wallet.topup("user-1", 5000.0, trip_id="trip-cab")
    itinerary = ItineraryOption(
        itinerary_id="itin-cab",
        trip_id="trip-cab",
        legs=[single_cab_leg],
        total_price=single_cab_leg.price,
        total_duration_minutes=45.0,
        metadata={},
    )
    req = BookingRequest(
        trip_id="trip-cab",
        user_id="user-1",
        itinerary=itinerary,
        user_confirmed=True,
        metadata={},
    )
    result = booking_agent.book_itinerary(req)
    assert result.status == "confirmed"
    assert result.all_confirmed is True
    assert len(result.leg_confirmations) == 1
    leg = result.leg_confirmations[0]
    assert leg.status == "confirmed"
    assert leg.booking_ref is not None
    assert leg.booking_ref.startswith("CAB-")
    assert result.total_charged == pytest.approx(450.0)
    assert wallet.get_balance("user-1").balance == pytest.approx(4550.0)


def test_successful_multi_leg_booking(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    booking_request: BookingRequest,
) -> None:
    wallet.topup("user-demo", 10000.0, trip_id=booking_request.trip_id)
    result = booking_agent.book_itinerary(booking_request)
    assert result.status == "confirmed"
    assert result.all_confirmed is True
    assert len(result.leg_confirmations) == 3
    assert all(lc.booking_ref for lc in result.leg_confirmations)
    assert result.total_charged == pytest.approx(450.0 + 4200.0 + 850.0)
    # one debit per leg
    debits = [
        tx
        for tx in wallet.get_ledger("user-demo", trip_id=booking_request.trip_id)
        if tx.type == "debit"
    ]
    assert len(debits) == 3
    assert wallet.get_balance("user-demo").balance == pytest.approx(
        10000.0 - result.total_charged
    )


def test_booking_references_returned(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    booking_request: BookingRequest,
) -> None:
    wallet.topup("user-demo", 10000.0, trip_id="t")
    result = booking_agent.book_itinerary(booking_request)
    refs = [lc.booking_ref for lc in result.leg_confirmations]
    assert all(r is not None for r in refs)
    modes = [lc.mode for lc in result.leg_confirmations]
    assert TransportMode.CAB in modes
    assert TransportMode.FLIGHT in modes


def test_insufficient_balance_prevents_operator_calls(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    booking_request: BookingRequest,
) -> None:
    # No top-up — zero balance
    result = booking_agent.book_itinerary(booking_request)
    assert result.status == "failed"
    assert result.all_confirmed is False
    assert "Insufficient funds" in (result.error or "")
    assert result.total_charged == 0.0
    assert result.leg_confirmations == []
    # No wallet debits
    ledger = wallet.get_ledger("user-demo")
    assert all(tx.type != "debit" for tx in ledger)


def test_user_consent_required(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    multi_leg_itinerary: ItineraryOption,
) -> None:
    wallet.topup("user-demo", 10000.0, trip_id="t")
    req = BookingRequest(
        trip_id="trip-no-consent",
        user_id="user-demo",
        itinerary=multi_leg_itinerary.model_copy(
            update={"trip_id": "trip-no-consent"}
        ),
        user_confirmed=False,
        metadata={},
    )
    with pytest.raises(BookingConsentRequiredError):
        booking_agent.book_itinerary(req)
    assert wallet.get_balance("user-demo").balance == 10000.0


def test_unsupported_operator_raises(
    booking_agent: BookingAgent, wallet: WalletAgent
) -> None:
    wallet.topup("user-1", 5000.0, trip_id="t")
    bad_leg = make_leg(
        "leg-bad",
        TransportMode.CAB,
        "Lyft",  # not in catalog
        "Ahmedabad",
        "Ahmedabad Airport",
        400.0,
    )
    itinerary = ItineraryOption(
        itinerary_id="itin-bad",
        trip_id="trip-bad",
        legs=[bad_leg],
        total_price=400.0,
        total_duration_minutes=40.0,
        metadata={},
    )
    req = BookingRequest(
        trip_id="trip-bad",
        user_id="user-1",
        itinerary=itinerary,
        user_confirmed=True,
        metadata={},
    )
    with pytest.raises(UnsupportedOperatorError):
        booking_agent.book_itinerary(req)


def test_failed_second_leg_compensates_first(
    wallet: WalletAgent, tmp_booking_db: str
) -> None:
    agent = BookingAgent(
        wallet_agent=wallet,
        db_path=tmp_booking_db,
        failure_rate=0.0,
        latency_seconds=0.0,
        force_failure_legs={"leg-2"},
    )
    wallet.topup("user-1", 10000.0, trip_id="trip-comp")
    leg1 = make_leg(
        "leg-1", TransportMode.CAB, "Ola", "Ahmedabad", "Ahmedabad Airport", 450.0
    )
    leg2 = make_leg(
        "leg-2",
        TransportMode.FLIGHT,
        "IndiGo",
        "Ahmedabad Airport",
        "Mumbai Airport",
        4200.0,
        hours_offset=12,
    )
    itinerary = ItineraryOption(
        itinerary_id="itin-comp",
        trip_id="trip-comp",
        legs=[leg1, leg2],
        total_price=4650.0,
        total_duration_minutes=200.0,
        metadata={},
    )
    req = BookingRequest(
        trip_id="trip-comp",
        user_id="user-1",
        itinerary=itinerary,
        user_confirmed=True,
        metadata={},
    )
    result = agent.book_itinerary(req)
    assert result.status == "failed"
    assert result.all_confirmed is False
    assert "leg-2" in result.failed_legs

    # First leg compensated (cancelled) and second failed
    statuses = {lc.leg_id: lc.status for lc in result.leg_confirmations}
    assert statuses["leg-1"] == "cancelled"
    assert statuses["leg-2"] == "failed"

    # Wallet fully restored (topup - debit + refund = topup)
    assert wallet.get_balance("user-1").balance == pytest.approx(10000.0)
    ledger = wallet.get_ledger("user-1", trip_id="trip-comp")
    types = [tx.type for tx in ledger]
    assert "debit" in types
    assert "refund" in types
    debit_total = sum(tx.amount for tx in ledger if tx.type == "debit")
    refund_total = sum(tx.amount for tx in ledger if tx.type == "refund")
    assert debit_total == pytest.approx(refund_total)


def test_cancellation_refunds_exact_leg_amount(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    booking_request: BookingRequest,
) -> None:
    wallet.topup("user-demo", 10000.0, trip_id=booking_request.trip_id)
    result = booking_agent.book_itinerary(booking_request)
    assert result.status == "confirmed"
    leg = result.leg_confirmations[0]
    balance_before = wallet.get_balance("user-demo").balance

    cancel = booking_agent.cancel_leg(booking_request.trip_id, leg.leg_id)
    assert cancel.status == "cancelled"
    assert cancel.refund_amount == pytest.approx(leg.price_charged)
    assert cancel.wallet_balance_after == pytest.approx(
        balance_before + leg.price_charged
    )

    # Persisted state
    loaded = booking_agent.get_booking(booking_request.trip_id)
    assert loaded is not None
    cancelled = [lc for lc in loaded.leg_confirmations if lc.leg_id == leg.leg_id][0]
    assert cancelled.status == "cancelled"
    assert loaded.status == "partially_cancelled"


def test_repeated_cancellation_is_idempotent(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    booking_request: BookingRequest,
) -> None:
    wallet.topup("user-demo", 10000.0, trip_id=booking_request.trip_id)
    result = booking_agent.book_itinerary(booking_request)
    leg_id = result.leg_confirmations[0].leg_id
    c1 = booking_agent.cancel_leg(booking_request.trip_id, leg_id)
    bal_after_first = wallet.get_balance("user-demo").balance
    c2 = booking_agent.cancel_leg(booking_request.trip_id, leg_id)
    assert c2.status == "cancelled"
    assert c2.refund_amount == 0.0
    assert wallet.get_balance("user-demo").balance == bal_after_first
    assert "idempotent" in c2.message.lower()


def test_repeated_booking_does_not_duplicate_charges(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    booking_request: BookingRequest,
) -> None:
    wallet.topup("user-demo", 10000.0, trip_id=booking_request.trip_id)
    r1 = booking_agent.book_itinerary(booking_request)
    bal_after = wallet.get_balance("user-demo").balance
    r2 = booking_agent.book_itinerary(booking_request)
    assert r2.status == "confirmed"
    assert r2.total_charged == r1.total_charged
    assert wallet.get_balance("user-demo").balance == bal_after
    debits = [
        tx
        for tx in wallet.get_ledger("user-demo", trip_id=booking_request.trip_id)
        if tx.type == "debit"
    ]
    assert len(debits) == 3


def test_deterministic_mock_failure_injection(
    wallet: WalletAgent, tmp_booking_db: str
) -> None:
    agent = BookingAgent(
        wallet_agent=wallet,
        db_path=tmp_booking_db,
        failure_rate=0.0,
        latency_seconds=0.0,
        force_failure_legs={"leg-only"},
    )
    wallet.topup("user-1", 5000.0, trip_id="trip-fail")
    leg = make_leg(
        "leg-only", TransportMode.CAB, "Uber", "Ahmedabad", "Ahmedabad Airport", 500.0
    )
    itinerary = ItineraryOption(
        itinerary_id="itin-fail",
        trip_id="trip-fail",
        legs=[leg],
        total_price=500.0,
        total_duration_minutes=40.0,
        metadata={},
    )
    req = BookingRequest(
        trip_id="trip-fail",
        user_id="user-1",
        itinerary=itinerary,
        user_confirmed=True,
        metadata={},
    )
    result = agent.book_itinerary(req)
    assert result.status == "failed"
    assert result.leg_confirmations[0].status == "failed"
    assert wallet.get_balance("user-1").balance == 5000.0


def test_goal_context_preserved_in_booking(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    booking_request: BookingRequest,
) -> None:
    wallet.topup("user-demo", 10000.0, trip_id=booking_request.trip_id)
    assert booking_request.itinerary.goal_context is not None
    assert "Jio Institute" in booking_request.itinerary.goal_context.goal_statement
    result = booking_agent.book_itinerary(booking_request)
    assert result.status == "confirmed"
    # Goal context stored in DB
    import sqlite3

    with sqlite3.connect(booking_agent.db_path) as conn:
        row = conn.execute(
            "SELECT goal_context_json FROM bookings WHERE trip_id = ?",
            (booking_request.trip_id,),
        ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert "Jio Institute" in row[0]


def test_book_single_leg_no_wallet_debit(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    single_cab_leg: LegOption,
) -> None:
    wallet.topup("user-1", 5000.0, trip_id="t")
    conf = booking_agent.book_single_leg("trip-x", single_cab_leg)
    assert conf.status == "confirmed"
    assert conf.booking_ref is not None
    # No debit from book_single_leg
    assert wallet.get_balance("user-1").balance == 5000.0


def test_get_booking_and_list_legs(
    booking_agent: BookingAgent,
    wallet: WalletAgent,
    booking_request: BookingRequest,
) -> None:
    wallet.topup("user-demo", 10000.0, trip_id=booking_request.trip_id)
    booking_agent.book_itinerary(booking_request)
    loaded = booking_agent.get_booking(booking_request.trip_id)
    assert loaded is not None
    assert loaded.trip_id == booking_request.trip_id
    legs = booking_agent.list_booked_legs(booking_request.trip_id)
    assert len(legs) == 3


def test_book_single_leg_force_failure(
    wallet: WalletAgent, tmp_booking_db: str, single_cab_leg: LegOption
) -> None:
    agent = BookingAgent(
        wallet_agent=wallet,
        db_path=tmp_booking_db,
        force_failure_legs={single_cab_leg.leg_id},
        failure_rate=0.0,
        latency_seconds=0.0,
    )
    conf = agent.book_single_leg("trip-f", single_cab_leg)
    assert conf.status == "failed"
    assert conf.booking_ref is None
