"""Shared pytest fixtures for Agent 3 and Agent 4 tests.

All tests use temporary SQLite databases and never touch data/*.db.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agents.agent3_booking import BookingAgent
from agents.agent4_wallet import WalletAgent
from api.schemas import (
    BookingRequest,
    GoalContext,
    ItineraryOption,
    LegOption,
    TransportMode,
)


@pytest.fixture
def tmp_wallet_db(tmp_path: Path) -> str:
    return str(tmp_path / "wallet.db")


@pytest.fixture
def tmp_booking_db(tmp_path: Path) -> str:
    return str(tmp_path / "bookings.db")


@pytest.fixture
def wallet(tmp_wallet_db: str) -> WalletAgent:
    return WalletAgent(db_path=tmp_wallet_db)


@pytest.fixture
def booking_agent(wallet: WalletAgent, tmp_booking_db: str) -> BookingAgent:
    return BookingAgent(
        wallet_agent=wallet,
        db_path=tmp_booking_db,
        failure_rate=0.0,
        latency_seconds=0.0,
    )


def _dt(hours_from_now: float = 12.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours_from_now)


@pytest.fixture
def sample_goal() -> GoalContext:
    return GoalContext(
        goal_statement=(
            "I have an interview tomorrow at Jio Institute in Navi Mumbai. "
            "I have one suitcase and need to arrive one hour early. "
            "I also need a return journey."
        ),
        purpose="interview",
        destination_name="Jio Institute",
        destination_address="Jio Institute, Navi Mumbai",
        appointment_time=_dt(24),
        return_required=True,
        luggage_count=1,
        required_buffer_minutes=60,
        metadata={"source": "test"},
    )


@pytest.fixture
def single_cab_leg() -> LegOption:
    dep = _dt(10)
    return LegOption(
        leg_id="leg-cab-1",
        mode=TransportMode.CAB,
        operator="Ola",
        origin="Ahmedabad",
        destination="Ahmedabad Airport",
        departure=dep,
        arrival=dep + timedelta(minutes=45),
        price=450.0,
        currency="INR",
        comfort_score=0.7,
        service_id="CAB-SVC-OLA",
        metadata={},
    )


@pytest.fixture
def multi_leg_itinerary(sample_goal: GoalContext) -> ItineraryOption:
    dep1 = _dt(10)
    leg1 = LegOption(
        leg_id="leg-1",
        mode=TransportMode.CAB,
        operator="Ola",
        origin="Ahmedabad",
        destination="Ahmedabad Airport",
        departure=dep1,
        arrival=dep1 + timedelta(minutes=45),
        price=450.0,
        comfort_score=0.7,
        metadata={},
    )
    leg2 = LegOption(
        leg_id="leg-2",
        mode=TransportMode.FLIGHT,
        operator="IndiGo",
        origin="Ahmedabad Airport",
        destination="Mumbai Airport",
        departure=dep1 + timedelta(hours=2),
        arrival=dep1 + timedelta(hours=3, minutes=35),
        price=4200.0,
        comfort_score=0.8,
        metadata={},
    )
    leg3 = LegOption(
        leg_id="leg-3",
        mode=TransportMode.CAB,
        operator="Uber",
        origin="Mumbai Airport",
        destination="Jio Institute",
        departure=dep1 + timedelta(hours=4),
        arrival=dep1 + timedelta(hours=5),
        price=850.0,
        comfort_score=0.75,
        metadata={},
    )
    total = leg1.price + leg2.price + leg3.price
    return ItineraryOption(
        itinerary_id="itin-jio-1",
        trip_id="trip-jio-1",
        goal_context=sample_goal,
        legs=[leg1, leg2, leg3],
        total_price=total,
        total_duration_minutes=300.0,
        total_emission_kg=95.0,
        score=0.91,
        explanation="Fastest end-to-end with 60 min buffer",
        metadata={"city_pair": "AMD-BOM"},
    )


@pytest.fixture
def booking_request(
    multi_leg_itinerary: ItineraryOption,
) -> BookingRequest:
    return BookingRequest(
        trip_id=multi_leg_itinerary.trip_id,
        user_id="user-demo",
        itinerary=multi_leg_itinerary,
        user_confirmed=True,
        idempotency_key="idem-trip-jio-1",
        metadata={},
    )


def make_leg(
    leg_id: str,
    mode: TransportMode,
    operator: str,
    origin: str,
    destination: str,
    price: float,
    hours_offset: float = 10.0,
) -> LegOption:
    dep = _dt(hours_offset)
    return LegOption(
        leg_id=leg_id,
        mode=mode,
        operator=operator,
        origin=origin,
        destination=destination,
        departure=dep,
        arrival=dep + timedelta(hours=1),
        price=price,
        comfort_score=0.6,
        metadata={},
    )
