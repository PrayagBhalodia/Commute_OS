"""Allowlisted, schema-validated tools for the conversational controller."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.schemas import (
    ConfirmPlanRequest,
    DisruptionRequest,
    FeedbackRequest,
    PlanRequest,
)
from llm.schemas import ExecutionTraceEntry
from orchestration.orchestrator import DMOSOrchestrator
from rag.retriever import KnowledgeRetriever
from tools.places_india import list_places

logger = logging.getLogger(__name__)


class StrictToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanJourneyInput(StrictToolInput):
    user_id: str = Field(min_length=1)
    goal_text: str = Field(min_length=3)
    origin: str | None = None
    origin_lat: float | None = Field(default=None, ge=-90, le=90)
    origin_lng: float | None = Field(default=None, ge=-180, le=180)
    destination: str | None = None
    appointment_time: str | None = None
    return_required: bool | None = None
    passenger_count: int = Field(default=1, ge=1, le=20)
    luggage_count: int | None = Field(default=None, ge=0, le=50)
    required_buffer_minutes: int | None = Field(default=None, ge=0, le=1440)
    max_options: int = Field(default=3, ge=1, le=5)
    preference_weights: dict[str, float] = Field(default_factory=dict)


class UserInput(StrictToolInput):
    user_id: str = Field(min_length=1)


class TopUpWalletInput(UserInput):
    amount: float = Field(gt=0, le=1_000_000)
    trip_id: str = "wallet"
    idempotency_key: str | None = None


class ConfirmBookingInput(UserInput):
    trip_id: str = Field(min_length=1)
    itinerary_id: str = Field(min_length=1)
    user_confirmed: Literal[True]
    idempotency_key: str | None = None


class LegOptionsInput(UserInput):
    trip_id: str = Field(min_length=1)
    itinerary_id: str = Field(min_length=1)


class ComposeLegsInput(UserInput):
    trip_id: str = Field(min_length=1)
    route_itinerary_id: str = Field(min_length=1)
    selected_leg_ids: dict[int, str]


class TriggerDisruptionInput(UserInput):
    trip_id: str = Field(min_length=1)
    leg_id: str | None = None
    reason: str = Field(default="traffic_delay", min_length=1)
    severity: Literal["low", "medium", "high"] = "medium"
    auto_rebook: bool = False


class FeedbackInput(UserInput):
    trip_id: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    liked: bool | None = None
    preferred_mode: str | None = None
    avoid_mode: str | None = None
    comment: str | None = Field(default=None, max_length=2000)
    selected_itinerary_id: str | None = None


class KnowledgeSearchInput(StrictToolInput):
    query: str = Field(min_length=2, max_length=2000)
    category: str | None = None
    top_k: int = Field(default=4, ge=1, le=20)


class PlacesSearchInput(StrictToolInput):
    query: str | None = None
    place_type: str | None = None


class EmptyInput(StrictToolInput):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], dict[str, Any]]


def _json_data(value: Any) -> Any:
    if isinstance(value, BaseModel):
        data = value.model_dump(mode="json")
    else:
        data = value
    if isinstance(data, dict):
        data = dict(data)
        data.pop("chain_of_thought", None)
    return data


class ToolRegistry:
    """A closed registry; unknown names and invalid arguments never execute."""

    def __init__(
        self,
        orchestrator: DMOSOrchestrator,
        retriever: KnowledgeRetriever,
    ) -> None:
        self.orchestrator = orchestrator
        self.retriever = retriever
        specs = [
            ToolSpec("plan_journey", "Plan ranked journeys for a structured travel goal.", PlanJourneyInput, self._plan),
            ToolSpec("get_wallet_balance", "Read a user's deterministic wallet balance.", UserInput, self._balance),
            ToolSpec("top_up_wallet", "Top up the simulated wallet after explicit user approval.", TopUpWalletInput, self._topup),
            ToolSpec("confirm_booking", "Confirm a planned itinerary; explicit user_confirmed=true is mandatory.", ConfirmBookingInput, self._confirm),
            ToolSpec("get_leg_options", "List validated compatible choices for every leg of a planned route.", LegOptionsInput, self._leg_options),
            ToolSpec("compose_journey", "Compose a final reviewable itinerary from the user's per-leg choices.", ComposeLegsInput, self._compose_legs),
            ToolSpec("trigger_disruption", "Run deterministic disruption handling for a booked trip.", TriggerDisruptionInput, self._disrupt),
            ToolSpec("get_user_preferences", "Read learned mobility preferences.", UserInput, self._preferences),
            ToolSpec("submit_feedback", "Submit explicit travel feedback.", FeedbackInput, self._feedback),
            ToolSpec("search_knowledge", "Search local policy and guidance documents; never use for live price or availability.", KnowledgeSearchInput, self._knowledge),
            ToolSpec("search_places", "Search the curated India places catalog.", PlacesSearchInput, self._places),
            ToolSpec("get_operator_catalog", "List supported simulated operators by mode.", EmptyInput, self._operators),
        ]
        self._specs = {spec.name: spec for spec in specs}

    @property
    def names(self) -> set[str]:
        return set(self._specs)

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.input_model.model_json_schema(),
                },
            }
            for spec in self._specs.values()
        ]

    def execute(
        self,
        name: str,
        payload: dict[str, Any],
        *,
        trace: list[ExecutionTraceEntry] | None = None,
    ) -> dict[str, Any]:
        event_log = trace if trace is not None else []
        spec = self._specs.get(name)
        if spec is None:
            event_log.append(
                ExecutionTraceEntry(
                    event="tool_rejected",
                    tool=name,
                    status="blocked",
                    detail="Unknown tool name.",
                )
            )
            return {"ok": False, "tool": name, "error": "unknown_tool"}
        try:
            validated = spec.input_model.model_validate(payload)
        except ValidationError as exc:
            event_log.append(
                ExecutionTraceEntry(
                    event="tool_rejected",
                    tool=name,
                    status="blocked",
                    detail="Tool input validation failed.",
                )
            )
            return {
                "ok": False,
                "tool": name,
                "error": "validation_error",
                "details": exc.errors(include_url=False),
            }
        try:
            result = spec.handler(validated)
            event_log.append(
                ExecutionTraceEntry(
                    event=result.pop("_event", "tool_completed"),
                    tool=name,
                    detail=result.pop("_detail", "Validated tool completed."),
                )
            )
            return {"ok": True, "tool": name, "data": result}
        except Exception as exc:
            logger.exception("Tool %s failed", name)
            event_log.append(
                ExecutionTraceEntry(
                    event="tool_failed",
                    tool=name,
                    status="failed",
                    detail=type(exc).__name__,
                )
            )
            return {
                "ok": False,
                "tool": name,
                "error": type(exc).__name__,
                "message": str(exc),
            }

    def _plan(self, value: BaseModel) -> dict[str, Any]:
        data = PlanJourneyInput.model_validate(value)
        priority = None
        if data.preference_weights:
            priority = max(data.preference_weights, key=data.preference_weights.get)
            priority = {"fastest": "time", "cheapest": "cost"}.get(priority, priority)
        plan = self.orchestrator.plan(
            PlanRequest(
                user_id=data.user_id,
                goal_text=data.goal_text,
                origin=data.origin,
                origin_lat=data.origin_lat,
                origin_lng=data.origin_lng,
                destination=data.destination,
                appointment_time=data.appointment_time,
                return_required=data.return_required,
                luggage_count=data.luggage_count,
                required_buffer_minutes=data.required_buffer_minutes,
                max_options=data.max_options,
                metadata={
                    "passenger_count": data.passenger_count,
                    **({"priority": priority} if priority in {"time", "cost", "comfort"} else {}),
                },
            )
        )
        result = _json_data(plan)
        result["_event"] = "journey_planned" if plan.status == "planned" else "intent_parsed"
        result["_detail"] = f"Plan status: {plan.status}."
        return result

    def _leg_options(self, value: BaseModel) -> dict[str, Any]:
        data = LegOptionsInput.model_validate(value)
        groups = self.orchestrator.get_leg_options(
            data.trip_id, data.user_id, data.itinerary_id
        )
        return {
            "trip_id": data.trip_id,
            "route_itinerary_id": data.itinerary_id,
            "groups": groups,
            "_event": "leg_options_listed",
            "_detail": f"Listed choices for {len(groups)} journey legs.",
        }

    def _compose_legs(self, value: BaseModel) -> dict[str, Any]:
        data = ComposeLegsInput.model_validate(value)
        itinerary = self.orchestrator.compose_selected_legs(
            data.trip_id,
            data.user_id,
            data.route_itinerary_id,
            data.selected_leg_ids,
        )
        result = _json_data(itinerary)
        result["_event"] = "journey_composed"
        result["_detail"] = "Validated leg selections and composed final journey."
        return result

    def _balance(self, value: BaseModel) -> dict[str, Any]:
        data = UserInput.model_validate(value)
        result = _json_data(self.orchestrator.wallet.get_balance(data.user_id))
        result["_event"] = "wallet_balance_read"
        return result

    def _topup(self, value: BaseModel) -> dict[str, Any]:
        data = TopUpWalletInput.model_validate(value)
        state = self.orchestrator.wallet.topup(
            data.user_id,
            data.amount,
            data.trip_id,
            "Chat-approved wallet top-up",
            idempotency_key=data.idempotency_key
            or f"chat-topup-{uuid.uuid4().hex}",
        )
        result = _json_data(state)
        result["_event"] = "wallet_topped_up"
        return result

    def _confirm(self, value: BaseModel) -> dict[str, Any]:
        data = ConfirmBookingInput.model_validate(value)
        existing = self.orchestrator.booking.get_booking(data.trip_id)
        if existing is not None:
            return {
                "status": "duplicate_blocked",
                "booking": _json_data(existing),
                "_event": "duplicate_booking_prevented",
                "_detail": "Existing booking returned; no second booking attempted.",
            }
        response = self.orchestrator.confirm_and_book(
            ConfirmPlanRequest(
                trip_id=data.trip_id,
                user_id=data.user_id,
                itinerary_id=data.itinerary_id,
                user_confirmed=data.user_confirmed,
                idempotency_key=data.idempotency_key
                or f"chat-book-{data.trip_id}-{data.itinerary_id}",
            )
        )
        result = _json_data(response)
        result["_event"] = (
            "booking_confirmed"
            if response.status == "confirmed"
            else "booking_not_confirmed"
        )
        result["_detail"] = f"Booking status: {response.status}."
        return result

    def _disrupt(self, value: BaseModel) -> dict[str, Any]:
        data = TriggerDisruptionInput.model_validate(value)
        response = self.orchestrator.handle_disruption(
            DisruptionRequest(**data.model_dump())
        )
        result = _json_data(response)
        result["_event"] = "alternatives_generated"
        result["_detail"] = f"Disruption status: {response.status}."
        return result

    def _preferences(self, value: BaseModel) -> dict[str, Any]:
        data = UserInput.model_validate(value)
        result = _json_data(self.orchestrator.get_preferences(data.user_id))
        result["_event"] = "preferences_read"
        return result

    def _feedback(self, value: BaseModel) -> dict[str, Any]:
        data = FeedbackInput.model_validate(value)
        result = _json_data(
            self.orchestrator.submit_feedback(FeedbackRequest(**data.model_dump()))
        )
        result["_event"] = "feedback_recorded"
        return result

    def _knowledge(self, value: BaseModel) -> dict[str, Any]:
        data = KnowledgeSearchInput.model_validate(value)
        results = self.retriever.search_knowledge(
            data.query, data.category, data.top_k
        )
        return {
            "results": [_json_data(item) for item in results],
            "_event": "knowledge_retrieved",
            "_detail": f"Retrieved {len(results)} policy chunks.",
        }

    def _places(self, value: BaseModel) -> dict[str, Any]:
        data = PlacesSearchInput.model_validate(value)
        return {
            "places": list_places(query=data.query, place_type=data.place_type),
            "_event": "places_searched",
        }

    def _operators(self, value: BaseModel) -> dict[str, Any]:
        EmptyInput.model_validate(value)
        return {
            "operators": self.orchestrator.booking.get_operator_catalog(),
            "_event": "operator_catalog_read",
        }
