"""Multi-turn conversational controller above the deterministic DMOS tools."""

from __future__ import annotations

import json
import re
from typing import Any

from llm.client import OpenAICompatibleClient
from llm.conversation_memory import ConversationMemory
from llm.prompts import state_context
from llm.schemas import (
    ChatMessageRequest,
    ChatMessageResponse,
    Citation,
    ConversationState,
    ExecutionTraceEntry,
    SuggestedAction,
)
from llm.tool_registry import ToolRegistry


POLICY_TERMS = {
    "baggage", "bag allowance", "refund policy", "cancellation policy",
    "metro rule", "railway rule", "train rule", "airport buffer",
    "how early", "accessibility", "wheelchair", "safety", "policy",
    "connection time", "transfer guideline",
}
TRAVEL_TERMS = {
    "travel", "trip", "journey", "reach", "go to", "get to", "commute",
    "flight", "train", "cab", "interview", "meeting", "airport",
}


class ConversationAgent:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        memory: ConversationMemory | None = None,
        client: OpenAICompatibleClient | None = None,
    ) -> None:
        self.registry = registry
        self.memory = memory or ConversationMemory()
        self.client = client or OpenAICompatibleClient()

    @staticmethod
    def _contains_any(text: str, terms: set[str]) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _clean_place(value: str) -> str:
        value = re.split(
            r"\b(?:today|tomorrow|tonight|by|before|with|carrying|"
            r"and return|returning|for an?|prioriti[sz]e|prefer)\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return value.strip(" ,.;")

    def _extract_constraints(self, state: ConversationState, message: str) -> None:
        text = message.strip()
        lower = text.lower()
        constraints = state.constraints

        match = re.search(
            r"\bfrom\s+(.+?)\s+to\s+(.+?)(?=$|[,.]|\s+tomorrow\b|"
            r"\s+today\b|\s+by\b|\s+with\b|\s+and\s+return\b|\s+for\b)",
            text,
            re.IGNORECASE,
        )
        if match:
            constraints.origin = self._clean_place(match.group(1))
            constraints.destination = self._clean_place(match.group(2))
        else:
            match = re.search(
                r"\bto\s+(.+?)\s+from\s+(.+?)(?=$|[,.]|\s+tomorrow\b|"
                r"\s+today\b|\s+by\b|\s+with\b)",
                text,
                re.IGNORECASE,
            )
            if match:
                constraints.destination = self._clean_place(match.group(1))
                constraints.origin = self._clean_place(match.group(2))
            elif constraints.destination is None:
                destination_only = re.search(
                    r"\b(?:go|travel|journey|trip|commute|get|reach).*?\bto\s+(.+?)(?=$|[,.]|\s+tomorrow\b|\s+today\b|\s+by\b)",
                    text,
                    re.IGNORECASE,
                )
                if destination_only:
                    constraints.destination = self._clean_place(destination_only.group(1))

        if "return" in lower or "round trip" in lower:
            constraints.return_required = True
        elif "one way" in lower:
            constraints.return_required = False

        bag = re.search(r"\b(\d+)\s*(?:bags?|suitcases?|luggage)\b", lower)
        if bag:
            constraints.luggage_count = int(bag.group(1))
        elif re.search(r"\b(?:a|one)\s+(?:bag|suitcase)\b", lower):
            constraints.luggage_count = 1

        passengers = re.search(
            r"\b(\d+)\s*(?:passengers?|people|travellers?|travelers?)\b",
            lower,
        )
        if passengers:
            constraints.passenger_count = max(1, int(passengers.group(1)))

        deadline = re.search(
            r"\b(?:by|before|at)\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
            lower,
        )
        if deadline:
            constraints.deadline = deadline.group(1)
        elif "tomorrow" in lower:
            constraints.deadline = "tomorrow"
        elif "today" in lower:
            constraints.deadline = "today"

        weights = constraints.preference_weights
        if any(word in lower for word in ("fastest", "quickest", "time")):
            weights["time"] = 1.0
        if any(word in lower for word in ("cheapest", "budget", "low cost")):
            weights["cost"] = 1.0
        if any(word in lower for word in ("comfort", "comfortable")):
            weights["comfort"] = 1.0

        # A short answer after a targeted clarification fills only that slot.
        if len(text.split()) <= 8 and not match:
            if state.status == "waiting_for_origin":
                constraints.origin = self._clean_place(text)
            elif state.status == "waiting_for_destination":
                constraints.destination = self._clean_place(text)

    @staticmethod
    def _citations(results: list[dict[str, Any]]) -> list[Citation]:
        return [
            Citation(
                source=item["source"],
                section=item["section"],
                category=item["category"],
                score=float(item["score"]),
                excerpt=item["text"][:240],
            )
            for item in results
        ]

    @staticmethod
    def _policy_answer(results: list[dict[str, Any]]) -> str:
        if not results:
            return (
                "I could not find that in the local policy knowledge base. "
                "For current operator rules, verify with the operator directly."
            )
        passages = [item["text"].strip() for item in results[:2]]
        return " ".join(passages)

    @staticmethod
    def _plan_summary(data: dict[str, Any]) -> str:
        if data.get("status") != "planned":
            return data.get("message") or "I need more information to plan this trip."
        options = data.get("itineraries") or []
        lines = [
            f"I found {len(options)} ranked option(s) from "
            f"{data['origin']['name']} to {data['destination']['name']}:"
        ]
        for index, option in enumerate(options[:5], start=1):
            modes = " + ".join(leg["mode"] for leg in option.get("legs", []))
            lines.append(
                f"{index}. {modes}: INR {option['total_price']:.0f}, "
                f"{option['total_duration_minutes']:.0f} min"
            )
        lines.append("Choose a route option. I will then show choices for every leg.")
        return "\n".join(lines)

    @staticmethod
    def _leg_options_summary(groups: list[dict[str, Any]]) -> str:
        lines = ["Here are the compatible choices for each leg:"]
        for group in groups:
            lines.append(
                f"Leg {group['leg_number']}: {group['origin']} to {group['destination']}"
            )
            for index, option in enumerate(group["options"], start=1):
                lines.append(
                    f"  {index}. {option['mode']} with {option['operator']} - "
                    f"INR {option['price']:.0f}"
                )
        lines.append(
            "Choose any leg with 'leg 2 option 1', or review the defaults."
        )
        return "\n".join(lines)

    @staticmethod
    def _journey_review(itinerary: dict[str, Any]) -> dict[str, Any]:
        legs = itinerary.get("legs") or []
        return {
            "itinerary_id": itinerary.get("itinerary_id"),
            "total_price": itinerary.get("total_price", 0),
            "total_duration_minutes": itinerary.get("total_duration_minutes", 0),
            "departure": legs[0].get("departure") if legs else None,
            "arrival": legs[-1].get("arrival") if legs else None,
            "legs": legs,
            "booking_requires_confirmation": True,
        }

    @classmethod
    def _review_summary(cls, itinerary: dict[str, Any]) -> str:
        review = cls._journey_review(itinerary)
        lines = ["Final journey review:"]
        for index, leg in enumerate(review["legs"], start=1):
            lines.append(
                f"{index}. {leg['origin']} to {leg['destination']} by "
                f"{leg['mode']} ({leg['operator']}) - INR {leg['price']:.0f}"
            )
        lines.append(
            f"Total: INR {review['total_price']:.0f}, "
            f"{review['total_duration_minutes']:.0f} min."
        )
        lines.append(
            "Nothing has been booked. Say 'confirm booking' only if you approve this journey and wallet debit."
        )
        return "\n".join(lines)

    @staticmethod
    def _booking_authorized(text: str) -> bool:
        lower = text.lower()
        return bool(
            re.search(r"\b(confirm|book|purchase)\b", lower)
            and not re.search(r"\b(don't|do not|not now|cancel)\b", lower)
        )

    @staticmethod
    def _topup_authorized(text: str) -> bool:
        return bool(
            re.search(r"\b(top\s*up|add|credit)\b", text.lower())
            and re.search(r"(?:inr|rs\.?|₹)?\s*\d+", text.lower())
        )

    def _execute(
        self,
        name: str,
        payload: dict[str, Any],
        trace: list[ExecutionTraceEntry],
        tool_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        result = self.registry.execute(name, payload, trace=trace)
        tool_results.append(result)
        return result

    def _provider_turn(
        self,
        state: ConversationState,
        request: ChatMessageRequest,
        trace: list[ExecutionTraceEntry],
        tool_results: list[dict[str, Any]],
    ) -> tuple[str | None, str]:
        if not self.client.enabled:
            return None, "deterministic_fallback"
        messages = [
            {"role": turn.role, "content": turn.content}
            for turn in state.turns[-10:]
        ]
        messages.append(
            {
                "role": "system",
                "content": state_context(
                    state.model_dump_json(
                        exclude={"turns"},
                        exclude_none=True,
                    )
                ),
            }
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    "Runtime context: server/client time="
                    f"{request.client_time.isoformat() if request.client_time else 'not supplied'}, "
                    f"timezone={request.timezone or 'not supplied'}, "
                    f"device location shared={request.current_lat is not None}."
                ),
            }
        )
        response = self.client.respond(
            messages=messages,
            tool_definitions=self.registry.definitions(),
        )
        if response is None:
            trace.append(
                ExecutionTraceEntry(
                    event="llm_fallback",
                    status="completed",
                    detail="Provider unavailable; deterministic controller used.",
                )
            )
            return None, "deterministic_fallback"

        for call in response.tool_calls:
            payload = dict(call.arguments)
            payload.setdefault("user_id", request.user_id)
            if call.name == "confirm_booking":
                if not self._booking_authorized(request.message):
                    trace.append(
                        ExecutionTraceEntry(
                            event="waiting_for_consent",
                            tool=call.name,
                            status="blocked",
                            detail="Provider tool call lacked explicit user consent.",
                        )
                    )
                    continue
                payload.setdefault("trip_id", state.active_trip_id)
                payload.setdefault("itinerary_id", state.selected_itinerary_id)
                payload["user_confirmed"] = True
            if call.name == "top_up_wallet" and not self._topup_authorized(request.message):
                trace.append(
                    ExecutionTraceEntry(
                        event="approval_required",
                        tool=call.name,
                        status="blocked",
                        detail="Explicit top-up amount and approval required.",
                    )
                )
                continue
            result = self._execute(call.name, payload, trace, tool_results)
            if not result.get("ok"):
                continue
            data = result.get("data", {})
            if call.name == "plan_journey":
                state.active_trip_id = data.get("trip_id")
                options = data.get("itineraries") or []
                state.selected_itinerary_id = (
                    options[0].get("itinerary_id") if options else None
                )
                state.status = (
                    "waiting_for_consent"
                    if data.get("status") == "planned"
                    else data.get("status", "collecting_intent")
                )
                if state.status == "waiting_for_consent":
                    trace.append(
                        ExecutionTraceEntry(
                            event="waiting_for_consent",
                            tool="confirm_booking",
                            detail="A plan exists; explicit booking consent is required.",
                        )
                    )
                if not response.text:
                    response.text = self._plan_summary(data)
            elif call.name == "confirm_booking" and not response.text:
                status = data.get("status")
                response.text = (
                    "The simulated journey booking is confirmed."
                    if status == "confirmed"
                    else f"The booking was not confirmed: {status or 'tool failure'}."
                )
            elif call.name == "get_wallet_balance" and not response.text:
                response.text = (
                    f"Your simulated DMOS wallet balance is "
                    f"INR {data.get('balance', 0):.2f}."
                )
        return response.text or None, "llm"

    def handle(self, request: ChatMessageRequest) -> ChatMessageResponse:
        state = self.memory.get_or_create(
            session_id=request.session_id,
            user_id=request.user_id,
            autonomy_level=request.autonomy_level,
        )
        self.memory.add_turn(state, "user", request.message)
        trace = [
            ExecutionTraceEntry(
                event="intent_parsed",
                detail="Message parsed into compact travel constraints.",
            )
        ]
        tool_results: list[dict[str, Any]] = []
        citations: list[Citation] = []
        suggested_actions: list[SuggestedAction] = []
        leg_option_groups: list[dict[str, Any]] = []
        journey_review: dict[str, Any] | None = None
        self._extract_constraints(state, request.message)
        lower = request.message.lower()
        answer: str | None = None
        mode = "deterministic_fallback"

        if self._contains_any(lower, POLICY_TERMS):
            result = self._execute(
                "search_knowledge",
                {"query": request.message, "top_k": 4},
                trace,
                tool_results,
            )
            items = result.get("data", {}).get("results", []) if result["ok"] else []
            citations = self._citations(items)
            answer = self._policy_answer(items)

        elif "balance" in lower and "wallet" in lower:
            result = self._execute(
                "get_wallet_balance",
                {"user_id": request.user_id},
                trace,
                tool_results,
            )
            if result["ok"]:
                balance = result["data"]["balance"]
                answer = f"Your simulated DMOS wallet balance is INR {balance:.2f}."

        elif self._topup_authorized(request.message):
            amount_match = re.search(r"(?:inr|rs\.?|₹)?\s*(\d+(?:\.\d+)?)", lower)
            amount = float(amount_match.group(1)) if amount_match else 0.0
            result = self._execute(
                "top_up_wallet",
                {
                    "user_id": request.user_id,
                    "amount": amount,
                    "trip_id": state.active_trip_id or "wallet",
                    "idempotency_key": f"chat-{state.session_id}-topup-{len(state.turns)}",
                },
                trace,
                tool_results,
            )
            answer = (
                f"Top-up completed. Balance is INR {result['data']['balance']:.2f}."
                if result["ok"]
                else f"I could not complete the top-up: {result.get('message', result.get('error'))}."
            )

        elif re.search(r"\bleg\s*(\d+)\s+option\s*(\d+)\b", lower):
            match = re.search(r"\bleg\s*(\d+)\s+option\s*(\d+)\b", lower)
            leg_number, option_number = int(match.group(1)), int(match.group(2))
            if not state.active_trip_id or not state.route_itinerary_id:
                answer = "Choose a route option before selecting individual legs."
            else:
                result = self._execute(
                    "get_leg_options",
                    {
                        "trip_id": state.active_trip_id,
                        "itinerary_id": state.route_itinerary_id,
                        "user_id": request.user_id,
                    },
                    trace,
                    tool_results,
                )
                leg_option_groups = result.get("data", {}).get("groups", []) if result["ok"] else []
                group = next(
                    (item for item in leg_option_groups if item["leg_number"] == leg_number),
                    None,
                )
                if group is None or option_number > len(group["options"]):
                    answer = "That leg option is not available for the selected route."
                else:
                    state.selected_leg_ids[leg_number] = group["options"][option_number - 1]["leg_id"]
                    composed = self._execute(
                        "compose_journey",
                        {
                            "trip_id": state.active_trip_id,
                            "route_itinerary_id": state.route_itinerary_id,
                            "selected_leg_ids": state.selected_leg_ids,
                            "user_id": request.user_id,
                        },
                        trace,
                        tool_results,
                    )
                    if composed["ok"]:
                        itinerary = composed["data"]
                        state.selected_itinerary_id = itinerary["itinerary_id"]
                        state.status = "waiting_for_consent"
                        journey_review = self._journey_review(itinerary)
                        answer = self._review_summary(itinerary)
                        suggested_actions.append(
                            SuggestedAction(
                                id="confirm_booking",
                                label="Confirm booking",
                                message="Confirm booking",
                                kind="confirm",
                            )
                        )

        elif re.search(r"\boption\s*([1-5])\b", lower):
            number = int(re.search(r"\boption\s*([1-5])\b", lower).group(1))
            plan = (
                self.registry.orchestrator.get_plan(state.active_trip_id)
                if state.active_trip_id
                else None
            )
            if plan and number <= len(plan.itineraries):
                state.selected_itinerary_id = plan.itineraries[number - 1].itinerary_id
                state.route_itinerary_id = state.selected_itinerary_id
                state.selected_leg_ids = {
                    index: leg.leg_id
                    for index, leg in enumerate(plan.itineraries[number - 1].legs, start=1)
                }
                state.status = "choosing_legs"
                result = self._execute(
                    "get_leg_options",
                    {
                        "trip_id": state.active_trip_id,
                        "itinerary_id": state.route_itinerary_id,
                        "user_id": request.user_id,
                    },
                    trace,
                    tool_results,
                )
                leg_option_groups = result.get("data", {}).get("groups", []) if result["ok"] else []
                itinerary = plan.itineraries[number - 1].model_dump(mode="json")
                journey_review = self._journey_review(itinerary)
                answer = self._leg_options_summary(leg_option_groups)
                suggested_actions.append(
                    SuggestedAction(
                        id="review_journey",
                        label="Review defaults",
                        message="Review journey",
                    )
                )
            else:
                answer = "That option is not available in the active plan."

        elif "review" in lower and state.status == "choosing_legs":
            plan = self.registry.orchestrator.get_plan(state.active_trip_id) if state.active_trip_id else None
            itinerary = next(
                (item for item in plan.itineraries if item.itinerary_id == state.selected_itinerary_id),
                None,
            ) if plan else None
            if itinerary:
                raw = itinerary.model_dump(mode="json")
                journey_review = self._journey_review(raw)
                state.status = "waiting_for_consent"
                answer = self._review_summary(raw)
                suggested_actions.append(
                    SuggestedAction(id="confirm_booking", label="Confirm booking", message="Confirm booking", kind="confirm")
                )
            else:
                answer = "The selected journey is no longer available. Please plan again."

        elif self._booking_authorized(request.message):
            if not state.active_trip_id or not state.selected_itinerary_id:
                answer = "There is no active itinerary to book. Plan a journey first."
            else:
                result = self._execute(
                    "confirm_booking",
                    {
                        "trip_id": state.active_trip_id,
                        "itinerary_id": state.selected_itinerary_id,
                        "user_id": request.user_id,
                        "user_confirmed": True,
                        "idempotency_key": (
                            f"chat-{state.active_trip_id}-"
                            f"{state.selected_itinerary_id}"
                        ),
                    },
                    trace,
                    tool_results,
                )
                status = result.get("data", {}).get("status") if result["ok"] else None
                if status == "confirmed":
                    state.status = "booked"
                    answer = "The simulated journey booking is confirmed."
                elif status == "duplicate_blocked":
                    answer = "That trip is already booked; no duplicate booking was made."
                else:
                    answer = (
                        "The booking was not confirmed: "
                        f"{result.get('data', {}).get('message') or result.get('message') or result.get('error')}."
                    )

        elif any(word in lower for word in ("disruption", "delayed", "cancelled", "canceled")):
            if not state.active_trip_id:
                answer = "Tell me which active trip was disrupted."
            else:
                auto_rebook = state.autonomy_level.value == "full_auto"
                result = self._execute(
                    "trigger_disruption",
                    {
                        "trip_id": state.active_trip_id,
                        "user_id": request.user_id,
                        "reason": request.message[:200],
                        "severity": "medium",
                        "auto_rebook": auto_rebook,
                    },
                    trace,
                    tool_results,
                )
                answer = (
                    result.get("data", {}).get("message")
                    if result["ok"]
                    else "I could not process the disruption."
                )

        else:
            origin = state.constraints.origin
            destination = state.constraints.destination
            is_travel = (
                self._contains_any(lower, TRAVEL_TERMS)
                or state.status.startswith("waiting_for_")
                or state.status in {"awaiting_origin_choice", "choosing_legs"}
            )
            if is_travel and not origin:
                wants_current = bool(re.search(r"\b(current|my location|here)\b", lower))
                wants_manual = bool(re.search(r"\b(manual|enter|type)\b", lower))
                if wants_current and request.current_lat is not None and request.current_lng is not None:
                    state.constraints.origin = request.current_location_label or "Current location"
                    state.constraints.origin_lat = request.current_lat
                    state.constraints.origin_lng = request.current_lng
                    state.status = "waiting_for_destination"
                    if destination:
                        answer = f"Current location received. Your destination is {destination}. Shall I generate the journey options now?"
                        suggested_actions.append(
                            SuggestedAction(id="plan_now", label="Generate options", message="Plan the journey now")
                        )
                    else:
                        answer = "Current location received. Where do you need to go?"
                elif wants_current:
                    state.status = "waiting_for_location_permission"
                    answer = "Please allow location access in your browser, or enter your starting location manually."
                    suggested_actions.extend([
                        SuggestedAction(id="share_location", label="Share current location", message="Use my current location", kind="location"),
                        SuggestedAction(id="manual_origin", label="Enter manually", message="I will enter my starting location manually"),
                    ])
                elif wants_manual:
                    state.status = "waiting_for_origin"
                    answer = "Enter your starting location."
                else:
                    state.status = "awaiting_origin_choice"
                    answer = "Would you like to start from your current location, or enter a location manually?"
                    suggested_actions.extend([
                        SuggestedAction(id="share_location", label="Use current location", message="Use my current location", kind="location"),
                        SuggestedAction(id="manual_origin", label="Enter manually", message="I will enter my starting location manually"),
                    ])
            elif is_travel and not destination:
                state.status = "waiting_for_destination"
                answer = "Where do you need to go?"
            elif is_travel and origin and destination:
                goal = " ".join(
                    turn.content for turn in state.turns[-4:] if turn.role == "user"
                )
                result = self._execute(
                    "plan_journey",
                    {
                        "user_id": request.user_id,
                        "goal_text": goal,
                        "origin": origin,
                        "origin_lat": state.constraints.origin_lat,
                        "origin_lng": state.constraints.origin_lng,
                        "destination": destination,
                        "return_required": state.constraints.return_required,
                        "passenger_count": state.constraints.passenger_count,
                        "luggage_count": state.constraints.luggage_count,
                        "preference_weights": state.constraints.preference_weights,
                    },
                    trace,
                    tool_results,
                )
                if result["ok"]:
                    data = result["data"]
                    state.active_trip_id = data["trip_id"]
                    options = data.get("itineraries") or []
                    state.selected_itinerary_id = (
                        options[0]["itinerary_id"] if options else None
                    )
                    state.route_itinerary_id = None
                    state.selected_leg_ids = {}
                    state.status = (
                        "waiting_for_consent"
                        if data.get("status") == "planned"
                        else data.get("status", "collecting_intent")
                    )
                    if state.status == "waiting_for_consent":
                        trace.append(
                            ExecutionTraceEntry(
                                event="waiting_for_consent",
                                tool="confirm_booking",
                                detail=(
                                    "Ranked options are ready; explicit booking "
                                    "consent is required."
                                ),
                            )
                        )
                    answer = self._plan_summary(data)
                    suggested_actions.extend(
                        SuggestedAction(
                            id=f"route_{index}",
                            label=f"Route {index}",
                            message=f"Option {index}",
                        )
                        for index in range(1, min(5, len(options)) + 1)
                    )

        if answer is None:
            answer, mode = self._provider_turn(
                state, request, trace, tool_results
            )
        if answer is None:
            answer = (
                "I can plan a journey, check your wallet, explain travel "
                "policies, or help with an existing booking. What would you like to do?"
            )

        self.memory.add_turn(state, "assistant", answer)
        return ChatMessageResponse(
            session_id=state.session_id,
            user_id=state.user_id,
            message=answer,
            state=state,
            citations=citations,
            execution_trace=trace,
            tool_results=tool_results,
            mode=mode,
            suggested_actions=suggested_actions,
            leg_option_groups=leg_option_groups,
            journey_review=journey_review,
        )
