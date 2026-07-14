"""Pydantic v2 domain contracts for DMOS Agent 3 and Agent 4."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class TransportMode(str, Enum):
    """Supported transportation modes."""

    CAB = "cab"
    AUTO = "auto"
    FLIGHT = "flight"
    TRAIN = "train"
    BUS = "bus"
    METRO = "metro"


class GoalContext(BaseModel):
    """Preserves the user's original mobility goal."""

    goal_statement: str
    purpose: Optional[str] = None
    destination_name: Optional[str] = None
    destination_address: Optional[str] = None
    appointment_time: Optional[datetime] = None
    return_required: bool = False
    luggage_count: int = 0
    required_buffer_minutes: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegOption(BaseModel):
    """A single transport leg within an itinerary."""

    leg_id: str
    mode: TransportMode
    operator: str
    origin: str
    destination: str
    departure: datetime
    arrival: datetime
    price: float
    currency: str = "INR"
    comfort_score: float = 0.5
    emission_kg: Optional[float] = None
    service_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price")
    @classmethod
    def price_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("price must not be negative")
        return v

    @field_validator("comfort_score")
    @classmethod
    def comfort_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("comfort_score must be between 0 and 1")
        return v

    @model_validator(mode="after")
    def arrival_after_departure(self) -> LegOption:
        if self.arrival < self.departure:
            raise ValueError("arrival must not be earlier than departure")
        return self


class ItineraryOption(BaseModel):
    """A complete multi-leg itinerary selected for booking."""

    itinerary_id: str
    trip_id: str
    goal_context: Optional[GoalContext] = None
    legs: list[LegOption]
    total_price: float
    total_duration_minutes: float
    total_emission_kg: Optional[float] = None
    score: float = 0.0
    explanation: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("total_price")
    @classmethod
    def total_price_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("total_price must not be negative")
        return v

    @model_validator(mode="after")
    def validate_legs(self) -> ItineraryOption:
        if not self.legs:
            raise ValueError("itinerary must contain at least one leg")
        leg_ids = [leg.leg_id for leg in self.legs]
        if len(leg_ids) != len(set(leg_ids)):
            raise ValueError("all leg IDs must be unique")
        return self


class BookingRequest(BaseModel):
    """Request to book a resolved itinerary (requires explicit user consent)."""

    trip_id: str
    user_id: str
    itinerary: ItineraryOption
    user_confirmed: bool
    idempotency_key: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LegBookingConfirmation(BaseModel):
    """Confirmation result for a single booked (or failed) leg."""

    leg_id: str
    mode: TransportMode
    operator: str
    booking_ref: Optional[str] = None
    status: str
    price_charged: float
    message: str = ""
    created_at: datetime

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"confirmed", "failed", "cancelled", "pending"}
        if v not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return v


class BookingConfirmation(BaseModel):
    """Aggregate booking result for an entire itinerary."""

    trip_id: str
    user_id: str
    itinerary_id: str
    status: str
    leg_confirmations: list[LegBookingConfirmation]
    all_confirmed: bool
    total_charged: float
    failed_legs: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    created_at: datetime

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"confirmed", "failed", "partially_cancelled", "cancelled"}
        if v not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return v


class WalletState(BaseModel):
    """Current wallet balance for a user."""

    user_id: str
    balance: float
    currency: str = "INR"
    updated_at: datetime


class WalletTransaction(BaseModel):
    """Append-only ledger entry for a wallet movement."""

    transaction_id: str
    trip_id: str
    user_id: str
    type: str
    amount: float
    description: str
    timestamp: datetime
    balance_after: float
    idempotency_key: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"topup", "debit", "refund"}
        if v not in allowed:
            raise ValueError(f"type must be one of {sorted(allowed)}")
        return v

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("transaction amount must be positive")
        return v


class ReconciliationResult(BaseModel):
    """Result of reconciling original vs revised itinerary costs."""

    trip_id: str
    user_id: str
    original_total: float
    revised_total: float
    difference: float
    action: str
    wallet_balance_after: float
    transaction: Optional[WalletTransaction] = None
    message: str

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {"refund", "charge_more", "top_up_required", "no_action"}
        if v not in allowed:
            raise ValueError(f"action must be one of {sorted(allowed)}")
        return v


class CancelTripRequest(BaseModel):
    """Reason payload required when cancelling an entire trip.

    The structured category (plus optional note) is persisted with the
    booking and fed to the preference agent as a learning signal.
    """

    reason_category: str = Field(min_length=1)
    reason_note: Optional[str] = None


class CancelLegResult(BaseModel):
    """Result of cancelling a single booked leg."""

    trip_id: str
    leg_id: str
    status: str
    refund_amount: float
    wallet_balance_after: float
    message: str


class TopUpRequest(BaseModel):
    """API request body for wallet top-up."""

    amount: float = Field(..., gt=0, description="Top-up amount in INR (must be > 0)")
    trip_id: str = Field(default="wallet", description="Associated trip or wallet context id")
    description: str = "Wallet top-up"
    idempotency_key: Optional[str] = None


class ReconcileRequest(BaseModel):
    """API request body for itinerary cost reconciliation."""

    trip_id: str
    user_id: str
    original_total: float = Field(..., ge=0, description="Original itinerary total in INR")
    revised_total: float = Field(..., ge=0, description="Revised itinerary total in INR")


# ---------------------------------------------------------------------------
# Full-OS contracts (Agents 1, 2, 5 + orchestration)
# ---------------------------------------------------------------------------


class GeoPoint(BaseModel):
    """Latitude/longitude coordinate."""

    lat: float
    lng: float
    label: Optional[str] = None


class PlaceInfo(BaseModel):
    """Resolved place in India (or custom pin)."""

    place_id: str
    name: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    lat: float
    lng: float
    place_type: str = "city"  # city | airport | landmark | custom
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserPreferences(BaseModel):
    """Learned / stated mobility preferences for a user."""

    user_id: str
    preferred_modes: list[str] = Field(default_factory=lambda: ["cab", "flight", "metro"])
    avoid_modes: list[str] = Field(default_factory=list)
    max_budget_inr: Optional[float] = None
    prefer_cheapest: bool = False
    prefer_fastest: bool = True
    prefer_comfort: bool = False
    prefer_low_emission: bool = False
    default_buffer_minutes: int = 45
    home_label: Optional[str] = None
    home_lat: Optional[float] = None
    home_lng: Optional[float] = None
    luggage_default: int = 0
    notes: list[str] = Field(default_factory=list)
    interaction_count: int = 0
    updated_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentResult(BaseModel):
    """Structured intent extracted by Agent 1."""

    user_id: str
    raw_text: str
    goal_context: GoalContext
    origin_hint: Optional[str] = None
    destination_hint: Optional[str] = None
    preferences: UserPreferences
    confidence: float = 0.7
    reasoning: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


class ThoughtStep(BaseModel):
    """One chain-of-thought step in the multi-agent orchestrator."""

    step_id: int
    phase: str  # thought | action | observation | decision | wait_user
    agent: Optional[str] = None
    title: str
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class PlanRequest(BaseModel):
    """Request to plan a trip from a natural-language goal (or structured fields)."""

    user_id: str
    goal_text: str
    origin: Optional[str] = None
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None
    destination: Optional[str] = None
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None
    appointment_time: Optional[datetime] = None
    return_required: Optional[bool] = None
    luggage_count: Optional[int] = None
    required_buffer_minutes: Optional[int] = None
    max_options: int = 3
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlanResponse(BaseModel):
    """Full planning response with CoT trace and ranked itineraries."""

    trip_id: str
    user_id: str
    intent: IntentResult
    origin: PlaceInfo
    destination: PlaceInfo
    distance_km: float
    itineraries: list[ItineraryOption]
    selected_itinerary_id: Optional[str] = None
    chain_of_thought: list[ThoughtStep] = Field(default_factory=list)
    status: str = "planned"  # planned | needs_input | failed
    message: str = ""


class ConfirmPlanRequest(BaseModel):
    """User selects an itinerary and consents to book."""

    trip_id: str
    user_id: str
    itinerary_id: str
    user_confirmed: bool = True
    topup_if_needed: Optional[float] = None
    idempotency_key: Optional[str] = None


class ConfirmPlanResponse(BaseModel):
    """Booking result after user confirmation, with CoT."""

    trip_id: str
    booking: Optional[BookingConfirmation] = None
    wallet_balance: Optional[float] = None
    chain_of_thought: list[ThoughtStep] = Field(default_factory=list)
    status: str
    message: str = ""


class FeedbackRequest(BaseModel):
    """User feedback used to learn preferences."""

    user_id: str
    trip_id: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    liked: Optional[bool] = None
    preferred_mode: Optional[str] = None
    avoid_mode: Optional[str] = None
    comment: Optional[str] = None
    selected_itinerary_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DisruptionRequest(BaseModel):
    """Simulate or report a disruption on a trip/leg."""

    trip_id: str
    user_id: str
    leg_id: Optional[str] = None
    reason: str = "traffic_delay"
    severity: str = "medium"  # low | medium | high
    auto_rebook: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class DisruptionResponse(BaseModel):
    """Result of disruption handling by Agent 5."""

    trip_id: str
    user_id: str
    disrupted_leg_id: Optional[str] = None
    cancelled_legs: list[str] = Field(default_factory=list)
    refund_total: float = 0.0
    revised_itinerary: Optional[ItineraryOption] = None
    rebooking: Optional[BookingConfirmation] = None
    reconciliation: Optional[ReconciliationResult] = None
    chain_of_thought: list[ThoughtStep] = Field(default_factory=list)
    status: str
    message: str = ""


class OrchestrateRequest(BaseModel):
    """End-to-end OS request: plan (and optionally auto-book if confirmed)."""

    plan: PlanRequest
    auto_book: bool = False
    itinerary_id: Optional[str] = None
    user_confirmed: bool = False
