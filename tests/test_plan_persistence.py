"""Plans must survive orchestrator restarts (SQLite-backed PlanStore)."""

from __future__ import annotations

from pathlib import Path

from api.schemas import PlanRequest
from orchestration.orchestrator import DMOSOrchestrator


def _orch(tmp_path: Path) -> DMOSOrchestrator:
    return DMOSOrchestrator(
        wallet_db=str(tmp_path / "w.db"),
        booking_db=str(tmp_path / "b.db"),
        profiles_db=str(tmp_path / "p.db"),
    )


def _plan(orch: DMOSOrchestrator):
    return orch.plan(
        PlanRequest(
            user_id="u1",
            goal_text="Meeting tomorrow at Jio Institute, one suitcase, arrive early",
            origin="Ahmedabad",
            destination="Jio Institute",
            max_options=2,
        )
    )


def test_plan_survives_restart(tmp_path: Path) -> None:
    plan = _plan(_orch(tmp_path))
    assert plan.status == "planned"

    # Simulate a server restart: a fresh orchestrator over the same DB files.
    restored = _orch(tmp_path).get_plan(plan.trip_id)
    assert restored is not None
    assert restored.trip_id == plan.trip_id
    assert [item.itinerary_id for item in restored.itineraries] == [
        item.itinerary_id for item in plan.itineraries
    ]


def test_selection_survives_restart(tmp_path: Path) -> None:
    from api.schemas import ConfirmPlanRequest

    first = _orch(tmp_path)
    first.wallet.topup("u1", 20000.0, trip_id="seed")
    plan = _plan(first)
    best = plan.itineraries[0]
    conf = first.confirm_and_book(
        ConfirmPlanRequest(
            trip_id=plan.trip_id,
            user_id="u1",
            itinerary_id=best.itinerary_id,
            user_confirmed=True,
        )
    )
    assert conf.status == "confirmed"

    restored = _orch(tmp_path).get_plan(plan.trip_id)
    assert restored is not None
    assert restored.selected_itinerary_id == best.itinerary_id


def test_plans_default_next_to_booking_db(tmp_path: Path) -> None:
    orch = _orch(tmp_path)
    assert Path(orch._plans.db_path) == tmp_path / "plans.db"
