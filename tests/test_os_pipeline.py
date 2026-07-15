"""Smoke tests for Agents 1/2/5 + orchestrator pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.agent1_intent import IntentAgent
from agents.agent2_journey import JourneyCompositionAgent
from agents.user_memory import UserMemoryStore
from api.schemas import ConfirmPlanRequest, DisruptionRequest, FeedbackRequest, PlanRequest
from orchestration.orchestrator import DMOSOrchestrator


@pytest.fixture
def orch(tmp_path: Path) -> DMOSOrchestrator:
    return DMOSOrchestrator(
        wallet_db=str(tmp_path / "w.db"),
        booking_db=str(tmp_path / "b.db"),
        profiles_db=str(tmp_path / "p.db"),
    )


def test_intent_parses_jio_interview(tmp_path: Path) -> None:
    mem = UserMemoryStore(db_path=str(tmp_path / "p.db"))
    agent = IntentAgent(memory=mem)
    result = agent.parse_intent(
        "u1",
        "Interview tomorrow at Jio Institute in Navi Mumbai with one suitcase, return same evening, one hour early",
    )
    assert result.goal_context.destination_name
    assert "jio" in result.goal_context.destination_name.lower()
    assert result.goal_context.luggage_count == 1
    assert result.goal_context.return_required is True
    assert result.goal_context.required_buffer_minutes == 60


def test_journey_composes_amd_to_jio() -> None:
    agent = JourneyCompositionAgent()
    from api.schemas import GoalContext, UserPreferences
    from datetime import datetime, timezone, timedelta

    goal = GoalContext(
        goal_statement="Interview at Jio",
        destination_name="Jio Institute",
        appointment_time=datetime.now(timezone.utc) + timedelta(days=1),
        return_required=False,
        luggage_count=1,
        required_buffer_minutes=60,
    )
    o, d, dist, opts, reasoning = agent.compose(
        user_id="u1",
        trip_id="t1",
        goal=goal,
        preferences=UserPreferences(user_id="u1"),
        origin_text="Ahmedabad",
        destination_text="Jio Institute",
        max_options=3,
    )
    assert o.name
    assert "Jio" in d.name or "jio" in d.name.lower()
    assert dist > 100
    assert len(opts) >= 1
    assert all(it.legs for it in opts)


def test_memory_learns_from_feedback(tmp_path: Path) -> None:
    mem = UserMemoryStore(db_path=str(tmp_path / "p.db"))
    prefs = mem.apply_feedback(
        "u1",
        comment="I want cheap options",
        preferred_mode="train",
        rating=4,
    )
    assert prefs.prefer_cheapest is True
    assert "train" in prefs.preferred_modes
    assert prefs.interaction_count >= 1


def test_memory_learns_optimisation_lens_from_journey_style(tmp_path: Path) -> None:
    mem = UserMemoryStore(db_path=str(tmp_path / "p.db"))
    # The user was optimising for Comfort when they gave positive feedback, so
    # the learned lens should switch to comfort (and drop the default fastest).
    prefs = mem.apply_feedback(
        "u2",
        liked=True,
        rating=5,
        metadata={"journey_style": "comfort"},
    )
    assert prefs.prefer_comfort is True
    assert prefs.prefer_fastest is False
    assert prefs.prefer_cheapest is False
    # Switching to a cost-optimised trip flips the lens again.
    prefs = mem.apply_feedback("u2", metadata={"journey_style": "cost"})
    assert prefs.prefer_cheapest is True
    assert prefs.prefer_comfort is False


def test_full_plan_confirm_book(orch: DMOSOrchestrator) -> None:
    orch.wallet.topup("u1", 20000.0, trip_id="seed")
    plan = orch.plan(
        PlanRequest(
            user_id="u1",
            goal_text="Meeting tomorrow at Jio Institute, one suitcase, arrive early",
            origin="Ahmedabad",
            destination="Jio Institute",
            max_options=2,
        )
    )
    assert plan.status == "planned"
    assert plan.itineraries
    assert plan.chain_of_thought
    best = plan.itineraries[0]
    conf = orch.confirm_and_book(
        ConfirmPlanRequest(
            trip_id=plan.trip_id,
            user_id="u1",
            itinerary_id=best.itinerary_id,
            user_confirmed=True,
        )
    )
    assert conf.status == "confirmed"
    assert conf.booking is not None
    assert conf.booking.all_confirmed is True
    assert conf.booking.total_charged > 0


def test_disruption_after_booking(orch: DMOSOrchestrator) -> None:
    orch.wallet.topup("u1", 25000.0, trip_id="seed")
    plan = orch.plan(
        PlanRequest(
            user_id="u1",
            goal_text="Interview at Jio Institute from Ahmedabad",
            origin="Ahmedabad",
            destination="Jio Institute",
        )
    )
    best = plan.itineraries[0]
    conf = orch.confirm_and_book(
        ConfirmPlanRequest(
            trip_id=plan.trip_id,
            user_id="u1",
            itinerary_id=best.itinerary_id,
            user_confirmed=True,
        )
    )
    assert conf.status == "confirmed"
    disrupt = orch.handle_disruption(
        DisruptionRequest(
            trip_id=plan.trip_id,
            user_id="u1",
            reason="traffic_delay",
            severity="medium",
            auto_rebook=True,
        )
    )
    assert disrupt.status in ("rerouted", "cancelled_only", "failed")
    assert disrupt.cancelled_legs
    assert disrupt.refund_total >= 0
