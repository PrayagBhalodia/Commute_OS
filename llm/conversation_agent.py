"""Multi-turn conversational controller above the deterministic DMOS tools."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
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
    "plan", "travel", "trip", "journey", "reach", "go to", "get to", "commute",
    "flight", "train", "cab", "interview", "meeting", "airport",
    "jana", "jaana", "pahuch", "pahunch", "safar", "sasta", "jaldi",
    "ghar se", "alternate dekho", "book kar", "wapas", "waapas",
}
HINGLISH_MARKERS = {
    "aap", "abhi", "batao", "bhai", "chahiye", "dekho", "ghar", "hai",
    "jaldi", "jana", "kar", "karo", "kal", "kya", "mujhe", "nahi",
    "paise", "pahuch", "sabse", "sasta", "tak", "zyada",
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
        value = re.sub(r"^(?:kal|aaj)\s+", "", value.strip(), flags=re.IGNORECASE)
        value = re.split(
            r"\b(?:today|tomorrow|tonight|by|before|with|carrying|"
            r"and return|returning|for an?|prioriti[sz]e|prefer|jana|jaana|"
            r"pahuchna|pahunchna|ke liye|kal|aaj)\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return value.strip(" ,.;")

    @staticmethod
    def _is_hinglish(text: str) -> bool:
        words = set(re.findall(r"[a-z]+", text.lower()))
        return len(words & HINGLISH_MARKERS) >= 2

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

        if constraints.origin is None or constraints.destination is None:
            hinglish_route = re.search(
                r"\b(.+?)\s+se\s+(.+?)\s+(?:jana|jaana|pahuchna|pahunchna|"
                r"travel|safar|jane|jaane)\b",
                text,
                re.IGNORECASE,
            )
            if hinglish_route:
                constraints.origin = self._clean_place(hinglish_route.group(1))
                constraints.destination = self._clean_place(hinglish_route.group(2))

        if re.search(r"\b(no return|without return|one way|one-way)\b", lower):
            constraints.return_required = False
        elif "return" in lower or "round trip" in lower or "wapas" in lower or "waapas" in lower:
            constraints.return_required = True
        elif state.status == "waiting_for_return" and re.search(r"\b(no|nahi)\b", lower):
            constraints.return_required = False
        elif state.status == "waiting_for_return" and re.search(r"\b(yes|haan|ha)\b", lower):
            constraints.return_required = True

        bag = re.search(r"\b(\d+)\s*(?:bags?|suitcases?|luggage)\b", lower)
        if bag:
            constraints.luggage_count = int(bag.group(1))
        elif re.search(r"\b(?:a|one|ek)\s+(?:bag|suitcase)\b", lower):
            constraints.luggage_count = 1

        passengers = re.search(
            r"\b(\d+)\s*(?:passengers?|people|travellers?|travelers?)\b",
            lower,
        )
        if passengers:
            constraints.passenger_count = max(1, int(passengers.group(1)))

        explicit_date = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", lower)
        if explicit_date:
            constraints.start_date = explicit_date.group(1)
        elif "tomorrow" in lower or "kal" in lower:
            constraints.start_date = "tomorrow"
        elif "today" in lower or "aaj" in lower:
            constraints.start_date = "today"

        start_time = re.search(
            r"\b(?:start(?:ing)?|depart(?:ing|ure)?|leave|at)\s+(?:at\s+)?"
            r"([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
            lower,
        )
        if start_time:
            constraints.start_time = start_time.group(1).strip()

        deadline = re.search(
            r"\b(?:by|before)\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
            lower,
        )
        if deadline:
            constraints.deadline = deadline.group(1).strip()

        weights = constraints.preference_weights
        if any(word in lower for word in ("fastest", "quickest", "time", "jaldi")):
            weights["time"] = 1.0
        if any(word in lower for word in ("cheapest", "budget", "low cost", "sasta")):
            weights["cost"] = 1.0
        if any(word in lower for word in ("comfort", "comfortable")):
            weights["comfort"] = 1.0

        # A short answer after a targeted clarification fills only that slot.
        if len(text.split()) <= 8 and not match:
            if state.status == "waiting_for_origin":
                constraints.origin = self._clean_place(text)
            elif state.status == "waiting_for_destination":
                constraints.destination = self._clean_place(text)
            elif state.status == "waiting_for_start_date":
                if explicit_date or any(word in lower for word in ("today", "tomorrow", "aaj", "kal")):
                    pass
                else:
                    constraints.start_date = text
            elif state.status == "waiting_for_start_time":
                simple_time = re.search(
                    r"\b([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
                    lower,
                )
                if simple_time:
                    constraints.start_time = simple_time.group(1).strip()

    @staticmethod
    def _citations(results: list[dict[str, Any]]) -> list[Citation]:
        return [
            Citation(
                source=item["source"],
                section=item["section"],
                category=item["category"],
                score=float(item["score"]),
                excerpt=item["text"][:240],
                source_url=item.get("source_url", ""),
                license=item.get("license", ""),
                updated_at=item.get("updated_at", ""),
                is_simulated=bool(item.get("is_simulated", False)),
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
                    f"{option.get('metadata', {}).get('specification', 'Standard')} - "
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
        return "\n".join(lines)

    @staticmethod
    def _resolved_start(state: ConversationState, request: ChatMessageRequest) -> str | None:
        raw_date = state.constraints.start_date
        raw_time = state.constraints.start_time
        if not raw_date or not raw_time:
            return None
        base = request.client_time or datetime.now(timezone.utc)
        lowered_date = raw_date.lower().strip()
        if lowered_date in {"today", "aaj"}:
            resolved_date = base.date()
        elif lowered_date in {"tomorrow", "kal"}:
            resolved_date = base.date() + timedelta(days=1)
        else:
            try:
                resolved_date = date.fromisoformat(raw_date.strip())
            except ValueError:
                match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", raw_date.strip())
                if not match:
                    return None
                resolved_date = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        cleaned_time = raw_time.lower().replace(" ", "")
        for pattern in ("%I:%M%p", "%I%p", "%H:%M", "%H"):
            try:
                resolved_time = datetime.strptime(cleaned_time, pattern).time()
                break
            except ValueError:
                continue
        else:
            return None
        return datetime.combine(resolved_date, resolved_time, tzinfo=base.tzinfo).isoformat()

    @staticmethod
    def _apply_saved_preferences(state: ConversationState, preferences: dict[str, Any]) -> None:
        state.saved_preferences = preferences
        weights = state.constraints.preference_weights
        if preferences.get("prefer_cheapest"):
            weights["cost"] = 1.0
        if preferences.get("prefer_fastest"):
            weights["time"] = 1.0
        if preferences.get("prefer_comfort"):
            weights["comfort"] = 1.0
        if state.constraints.luggage_count == 0:
            state.constraints.luggage_count = int(preferences.get("luggage_default") or 0)

    def _plan_ready_journey(
        self,
        state: ConversationState,
        request: ChatMessageRequest,
        trace: list[ExecutionTraceEntry],
        tool_results: list[dict[str, Any]],
    ) -> tuple[str, list[SuggestedAction]]:
        start_at = self._resolved_start(state, request)
        if start_at is None:
            state.constraints.start_time = None
            state.status = "waiting_for_start_time"
            return "Please enter a valid start time, for example 9:30 AM.", []
        goal = " ".join(turn.content for turn in state.turns[-8:] if turn.role == "user")
        result = self._execute(
            "plan_journey",
            {
                "user_id": request.user_id,
                "goal_text": goal,
                "origin": state.constraints.origin,
                "origin_lat": state.constraints.origin_lat,
                "origin_lng": state.constraints.origin_lng,
                "destination": state.constraints.destination,
                "appointment_time": start_at,
                "return_required": state.constraints.return_required,
                "passenger_count": state.constraints.passenger_count,
                "luggage_count": state.constraints.luggage_count,
                "preference_weights": state.constraints.preference_weights,
            },
            trace,
            tool_results,
        )
        if not result["ok"]:
            state.status = "planning_failed"
            return "I could not generate journey options. Please verify the trip details and try again.", []
        data = result["data"]
        state.active_trip_id = data["trip_id"]
        options = data.get("itineraries") or []
        state.selected_itinerary_id = options[0]["itinerary_id"] if options else None
        state.route_itinerary_id = None
        state.selected_leg_ids = {}
        state.status = "choosing_route" if data.get("status") == "planned" else data.get("status", "planning_failed")
        actions = [
            SuggestedAction(id=f"route_{index}", label=f"Route {index}", message=f"Option {index}")
            for index in range(1, min(5, len(options)) + 1)
        ]
        return self._plan_summary(data), actions

    def _wallet_handoff(
        self,
        state: ConversationState,
        user_id: str,
        total_price: float,
        trace: list[ExecutionTraceEntry],
        tool_results: list[dict[str, Any]],
    ) -> tuple[str, SuggestedAction]:
        result = self._execute(
            "get_wallet_balance", {"user_id": user_id}, trace, tool_results
        )
        balance = float(result.get("data", {}).get("balance", 0)) if result.get("ok") else 0.0
        state.wallet_balance = balance
        if balance < total_price:
            state.status = "waiting_for_wallet_topup"
            shortfall = total_price - balance
            return (
                f"Your wallet balance is INR {balance:.2f}, which is INR {shortfall:.2f} short. "
                "Please top up your wallet before proceeding.",
                SuggestedAction(id="open_wallet", label="Open wallet", message="Open wallet", kind="link", href="/wallet"),
            )
        state.status = "ready_for_booking_review"
        return (
            f"Your wallet balance is INR {balance:.2f}, which covers this journey. "
            "Please proceed to the Booking and Review page to finalize your trip.",
            SuggestedAction(
                id="booking_review",
                label="Booking and review",
                message="Open booking review",
                kind="link",
                href=f"/booking/{state.active_trip_id}",
            ),
        )

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
        wallet = self.registry.orchestrator.wallet.get_balance(request.user_id)
        preferences = self.registry.orchestrator.get_preferences(request.user_id)
        messages.append(
            {
                "role": "system",
                "content": (
                    "Runtime context: server/client time="
                    f"{request.client_time.isoformat() if request.client_time else 'not supplied'}, "
                    f"timezone={request.timezone or 'not supplied'}, "
                    f"device location shared={request.current_lat is not None}, "
                    f"wallet_balance_inr={wallet.balance:.2f}, "
                    f"saved_preferences={preferences.model_dump_json(exclude_none=True)}."
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
                trace.append(
                    ExecutionTraceEntry(
                        event="waiting_for_consent",
                        tool=call.name,
                        status="blocked",
                        detail="Booking consent is completed on the Booking and Review page.",
                    )
                )
                continue
            if call.name == "top_up_wallet":
                trace.append(
                    ExecutionTraceEntry(
                        event="approval_required",
                        tool=call.name,
                        status="blocked",
                        detail="VoyageAI cannot mutate the wallet; use the wallet page.",
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
        hinglish = self._is_hinglish(request.message)
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
            answer = "I cannot change your wallet from chat. Please use the wallet page to review and approve a top-up."
            suggested_actions.append(
                SuggestedAction(
                    id="open_wallet", label="Open wallet", message="Open wallet",
                    kind="link", href="/wallet",
                )
            )

        elif state.status == "waiting_for_preference_choice" and re.search(
            r"\b(usual|saved|default)\b", lower
        ):
            state.preference_mode = "usual"
            result = self._execute(
                "get_user_preferences", {"user_id": request.user_id}, trace, tool_results
            )
            if result["ok"]:
                self._apply_saved_preferences(state, result["data"])
            answer, suggested_actions = self._plan_ready_journey(
                state, request, trace, tool_results
            )

        elif state.status == "waiting_for_preference_choice" and re.search(
            r"\b(custom|explicit|specify|this trip|different)\b", lower
        ):
            state.preference_mode = "custom"
            answer, suggested_actions = self._plan_ready_journey(
                state, request, trace, tool_results
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
                    if state.preference_mode == "custom" and len(state.selected_leg_ids) < len(leg_option_groups):
                        remaining = next(
                            item["leg_number"] for item in leg_option_groups
                            if item["leg_number"] not in state.selected_leg_ids
                        )
                        state.status = "choosing_legs"
                        answer = f"Leg {leg_number} preference saved. Please choose an option for leg {remaining}."
                    else:
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
                            journey_review = self._journey_review(itinerary)
                            wallet_message, wallet_action = self._wallet_handoff(
                                state,
                                request.user_id,
                                float(itinerary.get("total_price", 0)),
                                trace,
                                tool_results,
                            )
                            answer = f"{self._review_summary(itinerary)}\n{wallet_message}"
                            suggested_actions.append(wallet_action)

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
                state.selected_leg_ids = (
                    {}
                    if state.preference_mode == "custom"
                    else {
                        index: leg.leg_id
                        for index, leg in enumerate(plan.itineraries[number - 1].legs, start=1)
                    }
                )
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
                if state.preference_mode != "custom":
                    suggested_actions.append(
                        SuggestedAction(
                            id="review_journey",
                            label="Review saved defaults",
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
                wallet_message, wallet_action = self._wallet_handoff(
                    state,
                    request.user_id,
                    float(raw.get("total_price", 0)),
                    trace,
                    tool_results,
                )
                answer = f"{self._review_summary(raw)}\n{wallet_message}"
                suggested_actions.append(wallet_action)
            else:
                answer = "The selected journey is no longer available. Please plan again."

        elif self._booking_authorized(request.message):
            if not state.active_trip_id or not state.selected_itinerary_id:
                answer = "There is no active itinerary to book. Plan a journey first."
            else:
                answer = "For safety, finalize consent and booking on the Booking and Review page."
                suggested_actions.append(
                    SuggestedAction(
                        id="booking_review",
                        label="Booking and review",
                        message="Open booking review",
                        kind="link",
                        href=f"/booking/{state.active_trip_id}",
                    )
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
                        if not state.constraints.start_date:
                            state.status = "waiting_for_start_date"
                            answer = f"Current location received. What date would you like to start your journey to {destination}?"
                        else:
                            state.status = "waiting_for_start_time"
                            answer = "Current location received. What time would you like to start?"
                    else:
                        answer = "Current location mil gaya. Kahan jana hai?" if hinglish else "Current location received. Where do you need to go?"
                elif wants_current:
                    state.status = "waiting_for_location_permission"
                    answer = ("Browser mein location allow karo, ya starting location manually enter karo." if hinglish else "Please allow location access in your browser, or enter your starting location manually.")
                    suggested_actions.extend([
                        SuggestedAction(id="share_location", label="Share current location", message="Use my current location", kind="location"),
                        SuggestedAction(id="manual_origin", label="Enter manually", message="I will enter my starting location manually"),
                    ])
                elif wants_manual:
                    state.status = "waiting_for_origin"
                    answer = "Starting location enter karo." if hinglish else "Enter your starting location."
                else:
                    state.status = "awaiting_origin_choice"
                    answer = ("Current location se start karna hai ya location manually enter karoge?" if hinglish else "Would you like to start from your current location, or enter a location manually?")
                    suggested_actions.extend([
                        SuggestedAction(id="share_location", label="Use current location", message="Use my current location", kind="location"),
                        SuggestedAction(id="manual_origin", label="Enter manually", message="I will enter my starting location manually"),
                    ])
            elif is_travel and not destination:
                state.status = "waiting_for_destination"
                answer = "Kahan jana hai?" if hinglish else "Where do you need to go?"
            elif is_travel and origin and destination and not state.constraints.start_date:
                state.status = "waiting_for_start_date"
                answer = "What date would you like to start your journey?"
            elif is_travel and origin and destination and not state.constraints.start_time:
                state.status = "waiting_for_start_time"
                answer = "What time would you like to start?"
            elif is_travel and origin and destination and state.constraints.return_required is None:
                state.status = "waiting_for_return"
                answer = "Do you need a return journey?"
                suggested_actions.extend(
                    [
                        SuggestedAction(id="return_yes", label="Yes, return", message="Yes, I need a return journey"),
                        SuggestedAction(id="return_no", label="No, one way", message="No, this is one way"),
                    ]
                )
            elif is_travel and origin and destination and state.preference_mode is None:
                state.status = "waiting_for_preference_choice"
                answer = "Would you like to use your usual saved preferences, or specify preferences for this trip?"
                suggested_actions.extend(
                    [
                        SuggestedAction(id="usual_preferences", label="Use usual", message="Use my usual saved preferences"),
                        SuggestedAction(id="custom_preferences", label="Specify this trip", message="I want custom preferences for this trip"),
                    ]
                )
            elif is_travel and origin and destination:
                answer, suggested_actions = self._plan_ready_journey(
                    state, request, trace, tool_results
                )
            elif re.search(r"\b(hi|hello|hey|namaste)\b", lower):
                answer = "Hi, where are you heading today?"

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
