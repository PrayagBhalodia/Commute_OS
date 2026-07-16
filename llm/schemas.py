"""Contracts for chat state, safe traces, citations, and API responses."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AutonomyLevel(str, Enum):
    MANUAL = "manual"
    SMART_APPROVAL = "smart_approval"
    FULL_AUTO = "full_auto"


class ConversationTurn(BaseModel):
    role: str
    content: str
    created_at: datetime = Field(default_factory=utc_now)


class TravelConstraints(BaseModel):
    origin: str | None = None
    origin_lat: float | None = None
    origin_lng: float | None = None
    destination: str | None = None
    # The broad place (state/city) the agent last asked the user to narrow;
    # repeating it or saying "just <place>" accepts it instead of looping.
    narrowing_prompted_for: str | None = None
    # The destination value that has been pinned down (specific enough, or
    # explicitly accepted as-is). Once set, that exact place is never narrowed
    # again, even as later slots like date/time are still being collected.
    destination_pinned: str | None = None
    start_date: str | None = None
    start_time: str | None = None
    deadline: str | None = None
    return_required: bool | None = None
    # Return-journey slots: the return can start/end somewhere different from
    # the onward destination/origin, so each is asked and stored separately.
    return_origin: str | None = None
    return_destination: str | None = None
    # Same broad-place narrowing tracking as the onward destination, but for the
    # return destination (the trip's final endpoint), pinned independently.
    return_narrowing_prompted_for: str | None = None
    return_destination_pinned: str | None = None
    return_date: str | None = None
    return_time: str | None = None
    passenger_count: int = 1
    luggage_count: int = 0
    preference_weights: dict[str, float] = Field(default_factory=dict)


class ConversationState(BaseModel):
    session_id: str
    user_id: str
    autonomy_level: AutonomyLevel = AutonomyLevel.MANUAL
    constraints: TravelConstraints = Field(default_factory=TravelConstraints)
    active_trip_id: str | None = None
    selected_itinerary_id: str | None = None
    route_itinerary_id: str | None = None
    selected_leg_ids: dict[int, str] = Field(default_factory=dict)
    preference_mode: str | None = None
    saved_preferences: dict[str, Any] = Field(default_factory=dict)
    wallet_balance: float | None = None
    status: str = "collecting_intent"
    turns: list[ConversationTurn] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


class Citation(BaseModel):
    source: str
    section: str
    category: str
    score: float
    excerpt: str
    source_url: str = ""
    license: str = ""
    updated_at: str = ""
    is_simulated: bool = False


class ExecutionTraceEntry(BaseModel):
    event: str
    tool: str | None = None
    status: str = "completed"
    detail: str = ""
    timestamp: datetime = Field(default_factory=utc_now)


class ChatMessageRequest(BaseModel):
    session_id: str | None = None
    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=8000)
    autonomy_level: AutonomyLevel | None = None
    client_time: datetime | None = None
    timezone: str | None = None
    current_lat: float | None = Field(default=None, ge=-90, le=90)
    current_lng: float | None = Field(default=None, ge=-180, le=180)
    current_location_label: str | None = Field(default=None, max_length=300)


class SuggestedAction(BaseModel):
    id: str
    label: str
    message: str
    kind: str = "message"
    href: str | None = None


class ChatMessageResponse(BaseModel):
    session_id: str
    user_id: str
    message: str
    state: ConversationState
    citations: list[Citation] = Field(default_factory=list)
    execution_trace: list[ExecutionTraceEntry] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = "deterministic_fallback"
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    leg_option_groups: list[dict[str, Any]] = Field(default_factory=list)
    journey_review: dict[str, Any] | None = None


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    category: str | None = None
    top_k: int = Field(default=4, ge=1, le=20)


class RagReindexRequest(BaseModel):
    rebuild: bool = False
