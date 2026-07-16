"""Multi-turn conversational controller above the deterministic DMOS tools."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from llm.client import LocalLoraClient, OpenAICompatibleClient, build_llm_client
from llm.conversation_memory import ConversationMemory
from llm.prompts import SLOT_FILLING_PROMPT, state_context
from llm.schemas import (
    ChatMessageRequest,
    ChatMessageResponse,
    Citation,
    ConversationState,
    ExecutionTraceEntry,
    SuggestedAction,
)
from llm.tool_registry import ToolRegistry
from tools.maps_api import classify_place, reverse_geocode


# "keep the broad place" signals when the agent asked to narrow a state/city.
ACCEPT_BROAD_RE = re.compile(
    r"\b(just|only|anywhere|fine|okay|ok|theek|wahi|city itself|main city)\b",
    re.IGNORECASE,
)

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
# Common conversational/function words that rule out treating a bare first
# message as a place name (e.g. "That looks interesting", "What can you
# help me with?" are chit-chat, not a destination like "Pune").
NON_PLACE_WORDS = {
    "what", "how", "why", "when", "who", "which", "this", "that",
    "can", "could", "would", "should", "will", "shall", "is", "are", "am",
    "do", "does", "did", "help", "looks", "look", "like", "interesting",
    "please", "thanks", "thank", "you", "your", "ok", "okay", "yes", "no",
    "good", "great", "nice", "cool", "sure", "maybe", "sorry", "want",
    "need", "tell", "know", "think",
}

# Trip variables collected during the intent phase, in the exact order the
# LLM wrapper (and the deterministic fallback) ask for them.
ONWARD_SLOTS = ("origin", "destination", "start_date", "start_time")
RETURN_SLOTS = ("return_origin", "return_destination", "return_date", "return_time")
# Every free-text slot the LLM is allowed to fill.
LLM_TEXT_SLOTS = ONWARD_SLOTS + RETURN_SLOTS
# slot name -> the conversation status used while that slot is outstanding.
SLOT_STATUS = {
    "origin": "waiting_for_origin",
    "destination": "waiting_for_destination",
    "start_date": "waiting_for_start_date",
    "start_time": "waiting_for_start_time",
    "return_required": "waiting_for_return",
    "return_origin": "waiting_for_return_origin",
    "return_destination": "waiting_for_return_destination",
    "return_date": "waiting_for_return_date",
    "return_time": "waiting_for_return_time",
}


class ConversationAgent:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        memory: ConversationMemory | None = None,
        client: OpenAICompatibleClient | LocalLoraClient | None = None,
    ) -> None:
        self.registry = registry
        self.memory = memory or ConversationMemory()
        self.client = client or build_llm_client()

    @staticmethod
    def _contains_any(text: str, terms: set[str]) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _clean_place(value: str) -> str:
        value = re.sub(r"^(?:kal|aaj)\s+", "", value.strip(), flags=re.IGNORECASE)
        value = re.split(
            r"\b(?:today|tomorrow|tonight|by|before|with|carrying|"
            r"and return|returning|for an?|prioriti[sz]e|prefer|jana|jaana|"
            r"pahuchna|pahunchna|ke liye|kal|aaj|on|at|starting|departing|"
            r"leaving)\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        return value.strip(" ,.;")

    @staticmethod
    def _is_hinglish(text: str) -> bool:
        words = set(re.findall(r"[a-z]+", text.lower()))
        return len(words & HINGLISH_MARKERS) >= 2

    @staticmethod
    def _resolve_current_location(request: ChatMessageRequest) -> str:
        """Real place name for shared device coordinates.

        Reverse-geocodes via LocationIQ/Nominatim (offline catalog as a
        fallback) so the chat, state, and itineraries show the actual place
        (e.g. "Navrangpura, Ahmedabad") instead of the generic
        "Current location" label.
        """
        place: dict[str, Any] | None = None
        try:
            place = reverse_geocode(request.current_lat, request.current_lng)
        except Exception:  # noqa: BLE001 — any geocoder failure falls back
            place = None
        if place:
            name = (place.get("name") or "").strip()
            if name.startswith("Pin ("):
                name = ""  # raw-coordinate pin, not a real place name
            city = (place.get("city") or "").strip()
            if name and city and city.lower() not in name.lower():
                return f"{name}, {city}"
            if name:
                return name
            if city:
                return city
        label = (request.current_location_label or "").strip()
        return label or "Current location"

    # ------------------------------------------------------------------
    # LLM slot-filling wrapper (primary conversational brain).
    #
    # The LLM extracts the trip variables from natural language; this
    # deterministic code decides which slot is still missing and whether the
    # trip is ready to plan, so the model can never skip a field or plan early.
    # ------------------------------------------------------------------
    @staticmethod
    def _first_missing_slot(constraints: Any) -> str | None:
        """Next trip variable to collect, honouring the return-journey rules."""
        for slot in ONWARD_SLOTS:
            if not getattr(constraints, slot):
                return slot
        if constraints.return_required is None:
            return "return_required"
        if constraints.return_required:
            for slot in RETURN_SLOTS:
                if not getattr(constraints, slot):
                    return slot
        return None

    @staticmethod
    def _apply_llm_slots(constraints: Any, slots: dict[str, Any]) -> None:
        """Merge the LLM's extracted variables into the stored constraints.

        Only non-empty values overwrite, so a later turn never wipes a slot the
        user already filled just because the model omitted it.
        """
        if not isinstance(slots, dict):
            return
        placeholders = {"current location", "my current location", "my location", "here"}
        for field in LLM_TEXT_SLOTS:
            value = slots.get(field)
            if isinstance(value, str) and value.strip():
                # Never let a generic placeholder overwrite a real place name
                # (device coordinates are resolved to an actual place upstream).
                if value.strip().lower() in placeholders and getattr(constraints, field):
                    continue
                setattr(constraints, field, value.strip())
        rr = slots.get("return_required")
        if isinstance(rr, bool):
            constraints.return_required = rr

    @staticmethod
    def _slot_actions(slot: str, constraints: Any) -> list[SuggestedAction]:
        """Quick-reply buttons that go with the question for a given slot."""
        if slot == "origin":
            return [
                SuggestedAction(id="share_location", label="Use current location", message="Use my current location", kind="location"),
                SuggestedAction(id="manual_origin", label="Enter manually", message="I will enter my starting location manually"),
            ]
        if slot == "return_required":
            return [
                SuggestedAction(id="return_yes", label="Yes, return", message="Yes, I need a return journey"),
                SuggestedAction(id="return_no", label="No, one way", message="No, this is one way"),
            ]
        if slot == "return_origin" and constraints.destination:
            return [SuggestedAction(id="return_origin_same", label=f"Same as {constraints.destination}", message=f"Same as {constraints.destination}")]
        if slot == "return_destination" and constraints.origin:
            return [SuggestedAction(id="return_destination_same", label=f"Same as {constraints.origin}", message=f"Same as {constraints.origin}")]
        return []

    @staticmethod
    def _default_slot_question(slot: str, constraints: Any, hinglish: bool) -> str:
        """Fallback question if the model doesn't supply its own phrasing."""
        questions = {
            "origin": "Where are you starting from?",
            "destination": "Where do you need to go?",
            "start_date": "What date would you like to start your journey?",
            "start_time": "What time would you like to start?",
            "return_required": "Do you need a return journey?",
            "return_origin": f"Where will your return journey start? It doesn't have to be {constraints.destination or 'your destination'}.",
            "return_destination": f"Where should the return journey end? It doesn't have to be {constraints.origin or 'your origin'}.",
            "return_date": "What date is the return journey?",
            "return_time": "What time would you like to start the return journey?",
        }
        return questions.get(slot, "Could you share a few more trip details?")

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any] | None:
        """Parse a JSON object out of an LLM reply, tolerating ```json fences."""
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return parsed if isinstance(parsed, dict) else None

    def _collect_intent_llm(
        self,
        state: ConversationState,
        request: ChatMessageRequest,
        trace: list[ExecutionTraceEntry],
        hinglish: bool,
    ) -> tuple[str | None, list[SuggestedAction], str | None]:
        """LLM-driven collection of the trip variables.

        Returns (answer, suggested_actions, mode). answer is None when the LLM
        provider is unavailable or its output was unusable, so the caller can
        fall back to the deterministic controller.
        """
        chat_fn = getattr(self.client, "chat", None)
        if not getattr(self.client, "enabled", False) or chat_fn is None:
            return None, [], None

        constraints = state.constraints
        known = {
            field: getattr(constraints, field)
            for field in (*LLM_TEXT_SLOTS, "return_required")
            if getattr(constraints, field) is not None
        }
        history = [
            {"role": turn.role, "content": turn.content}
            for turn in state.turns[-10:]
        ]
        directive = (
            "Known trip variables so far (do not re-ask these): "
            f"{json.dumps(known)}. Update them from the latest user message and "
            "ask for the next missing field in the required order. Respond with "
            "the JSON object only."
        )
        messages = [
            {"role": "system", "content": SLOT_FILLING_PROMPT},
            *history,
            {"role": "system", "content": directive},
        ]
        raw = chat_fn(messages=messages)
        if raw is None:
            trace.append(
                ExecutionTraceEntry(
                    event="llm_fallback",
                    status="completed",
                    detail="LLM provider unavailable; deterministic controller used.",
                )
            )
            return None, [], None

        data = self._parse_json(raw)
        if data is None:
            trace.append(
                ExecutionTraceEntry(
                    event="llm_fallback",
                    status="completed",
                    detail="LLM output was not valid JSON; deterministic controller used.",
                )
            )
            return None, [], None

        self._apply_llm_slots(constraints, data.get("slots") or {})
        trace.append(
            ExecutionTraceEntry(
                event="intent_parsed",
                detail="Trip variables extracted by VoyageAI (LLM slot-filling).",
            )
        )

        missing = self._first_missing_slot(constraints)
        if missing is None:
            # All variables collected — hand off to the deterministic planning
            # path via the preferences step.
            state.status = "waiting_for_preference_choice"
            return (
                "Would you like to use your usual saved preferences, or specify "
                "preferences for this trip?",
                [
                    SuggestedAction(id="usual_preferences", label="Use usual", message="Use my usual saved preferences"),
                    SuggestedAction(id="custom_preferences", label="Specify this trip", message="I want custom preferences for this trip"),
                ],
                "llm",
            )

        state.status = SLOT_STATUS.get(missing, "collecting_intent")
        reply = (data.get("reply") or "").strip() or self._default_slot_question(
            missing, constraints, hinglish
        )
        return reply, self._slot_actions(missing, constraints), "llm"

    def _place_narrowing_question(
        self,
        state: ConversationState,
        message: str,
        hinglish: bool,
        *,
        place_field: str = "destination",
        prompted_field: str = "narrowing_prompted_for",
        pinned_field: str = "destination_pinned",
        en_verb: str = "do you need to go",
        hi_verb: str = "jana hai",
    ) -> str | None:
        """Follow-up question when a place slot is a whole country/state/city.

        Classification comes from the live geocoder (works for any region
        worldwide), so "Texas" → where in Texas?, "Paris" → where in Paris?
        Repeating the same place (or "just <place>") accepts it as-is. The same
        drill-down serves the onward destination and the return destination by
        pointing it at different slot/tracking fields.
        """
        constraints = state.constraints
        place = (getattr(constraints, place_field) or "").strip()
        if not place:
            return None
        # Already pinned this exact place (accepted, or specific enough) — never
        # narrow it again, even while later slots (date/time) are collected.
        pinned = (getattr(constraints, pinned_field) or "").strip()
        if pinned and pinned.lower() == place.lower():
            return None
        prompted = (getattr(constraints, prompted_field) or "").strip()

        if prompted:
            if place.lower() == prompted.lower():
                # They repeated the broad place — keep it and move on.
                setattr(constraints, prompted_field, None)
                setattr(constraints, pinned_field, place)
                return None
            if (
                ACCEPT_BROAD_RE.search(message)
                and classify_place(place) == "unknown"
            ):
                # "Just Ahmedabad is fine" clobbered the slot with filler
                # text; restore the place they are accepting.
                setattr(constraints, place_field, prompted)
                setattr(constraints, prompted_field, None)
                setattr(constraints, pinned_field, prompted)
                return None

        specificity = classify_place(place)
        if specificity not in ("country", "state", "city"):
            setattr(constraints, prompted_field, None)
            setattr(constraints, pinned_field, place)
            return None

        setattr(constraints, prompted_field, place)
        if specificity in ("country", "state"):
            region_word = "country" if specificity == "country" else "state"
            return (
                f"{place} me kahan {hi_verb}? Koi city ya specific jagah batao."
                if hinglish
                else (
                    f"{place} is a whole {region_word} — where in {place} "
                    f"{en_verb}? A city or a specific place helps."
                )
            )
        return (
            f"{place} me exactly kahan? Koi locality ya landmark batao, "
            f"ya bolo 'just {place}'."
            if hinglish
            else (
                f"Where in {place} exactly — a locality, landmark, or "
                f"address? Say 'just {place}' if the city is enough."
            )
        )

    def _extract_constraints(self, state: ConversationState, message: str) -> None:
        text = message.strip()
        lower = text.lower()
        constraints = state.constraints

        match = re.search(
            r"\bfrom\s+(.+?)\s+to\s+(.+?)(?=$|[,.]|\s+tomorrow\b|"
            r"\s+today\b|\s+by\b|\s+with\b|\s+and\s+return\b|\s+for\b|"
            r"\s+on\b|\s+at\b|\s+starting\b|\s+departing\b|\s+leaving\b)",
            text,
            re.IGNORECASE,
        )
        if match:
            constraints.origin = self._clean_place(match.group(1))
            constraints.destination = self._clean_place(match.group(2))
        else:
            match = re.search(
                r"\bto\s+(.+?)\s+from\s+(.+?)(?=$|[,.]|\s+tomorrow\b|"
                r"\s+today\b|\s+by\b|\s+with\b|\s+on\b|\s+at\b)",
                text,
                re.IGNORECASE,
            )
            if match:
                constraints.destination = self._clean_place(match.group(1))
                constraints.origin = self._clean_place(match.group(2))
            elif constraints.destination is None:
                destination_only = re.search(
                    r"\b(?:go|travel|journey|trip|commute|get|reach).*?\bto\s+(.+?)"
                    r"(?=$|[,.]|\s+tomorrow\b|\s+today\b|\s+by\b|\s+on\b|\s+at\b)",
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

        awaiting_return_slot = state.status in (
            "waiting_for_return_origin",
            "waiting_for_return_destination",
            "waiting_for_return_date",
            "waiting_for_return_time",
        )
        if re.search(r"\b(no return|without return|one way|one-way)\b", lower):
            constraints.return_required = False
        elif not awaiting_return_slot and (
            "return" in lower or "round trip" in lower or "wapas" in lower or "waapas" in lower
        ):
            constraints.return_required = True
        elif state.status == "waiting_for_return" and re.search(r"\b(no|nahi)\b", lower):
            constraints.return_required = False
        elif state.status == "waiting_for_return" and re.search(r"\b(yes|haan|ha)\b", lower):
            constraints.return_required = True

        # Return-journey details volunteered inline, e.g. "returning on
        # 2026-07-20 at 6 pm from Gandhinagar".
        return_date_match = re.search(
            r"\breturn(?:ing)?\b[^.;]*?\b(?:on\s+)?(20\d{2}-\d{2}-\d{2}|tomorrow|today)\b",
            lower,
        )
        if return_date_match:
            constraints.return_date = return_date_match.group(1)
        return_time_match = re.search(
            r"\breturn(?:ing)?\b[^.;]*?\b(?:at|by)\s+"
            r"([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
            lower,
        )
        if return_time_match:
            constraints.return_time = return_time_match.group(1).strip()

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
        date_value: str | None = None
        if explicit_date:
            date_value = explicit_date.group(1)
        elif "tomorrow" in lower or "kal" in lower:
            date_value = "tomorrow"
        elif "today" in lower or "aaj" in lower:
            date_value = "today"
        if date_value:
            # A date given while the agent asked for the return date fills the
            # return slot; it must not clobber the onward start date.
            if state.status == "waiting_for_return_date":
                constraints.return_date = date_value
            else:
                constraints.start_date = date_value

        start_time = re.search(
            r"\b(?:start(?:ing)?|depart(?:ing|ure)?|leave|at)\s+(?:at\s+)?"
            r"([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
            lower,
        )
        if start_time and (
            return_time_match is None
            or start_time.start(1) != return_time_match.start(1)
        ):
            if state.status == "waiting_for_return_time":
                constraints.return_time = start_time.group(1).strip()
            else:
                constraints.start_time = start_time.group(1).strip()

        deadline = re.search(
            r"\b(?:by|before)\s+([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
            lower,
        )
        if deadline:
            constraints.deadline = deadline.group(1).strip()
            # This app tracks a single time anchor per leg, so an "arrive
            # by/before <time>" deadline also satisfies the start_time (or
            # return_time) slot instead of being silently dropped and asked
            # for again.
            if state.status == "waiting_for_return_time":
                if not constraints.return_time:
                    constraints.return_time = constraints.deadline
            elif not constraints.start_time:
                constraints.start_time = constraints.deadline

        weights = constraints.preference_weights
        if any(word in lower for word in ("fastest", "quickest", "time", "jaldi")):
            weights["time"] = 1.0
        if any(word in lower for word in ("cheapest", "budget", "low cost", "sasta")):
            weights["cost"] = 1.0
        if any(word in lower for word in ("comfort", "comfortable")):
            weights["comfort"] = 1.0

        # A short answer after a targeted clarification fills only that slot.
        if len(text.split()) <= 8 and not match:
            simple_time = re.search(
                r"\b([0-9]{1,2}(?::[0-9]{2})?\s*(?:am|pm)?)\b",
                lower,
            )
            # "Use my current location" is a quick-reply button, not a typed
            # place name — capturing it literally would corrupt the slot and
            # pre-empt the device-coordinate resolution in handle(), which
            # runs later and needs to see the slot still empty.
            location_intent = re.search(r"\b(current location|my location)\b", lower) is not None
            # A typed place name while we are still offering the "current vs
            # manual" origin choice is the origin itself (e.g. the origin
            # autocomplete submits "Mumbai Airport") — capture it instead of
            # re-asking. The manual-entry quick-reply is not a place name.
            manual_intent = re.search(r"\b(manual|manually|enter|type)\b", lower) is not None
            if state.status in ("waiting_for_origin", "awaiting_origin_choice"):
                if not location_intent and not manual_intent:
                    constraints.origin = self._clean_place(text)
            elif state.status == "waiting_for_destination":
                if not location_intent:
                    constraints.destination = self._clean_place(text)
            elif (
                state.status == "collecting_intent"
                and len(state.turns) == 1
                and constraints.origin is None
                and constraints.destination is None
                and not location_intent
                and not simple_time
                and not date_value
                and "?" not in text
                and len(text.split()) <= 4
                and not self._contains_any(lower, POLICY_TERMS)
                and not self._contains_any(lower, TRAVEL_TERMS)
                and not (set(re.findall(r"[a-z']+", lower)) & NON_PLACE_WORDS)
            ):
                # A bare first message ("Pune") before any question has been
                # asked is almost always the traveller naming their
                # destination — matching the "where are you heading?"
                # greeting — so capture it instead of silently dropping it
                # and asking for the origin first.
                constraints.destination = self._clean_place(text)
            elif state.status == "waiting_for_start_date":
                if not date_value:
                    constraints.start_date = text
            elif state.status == "waiting_for_start_time":
                if simple_time:
                    constraints.start_time = simple_time.group(1).strip()
            elif state.status == "waiting_for_return_origin":
                if re.search(r"\b(same|wahi)\b", lower) and constraints.destination:
                    constraints.return_origin = constraints.destination
                elif not location_intent:
                    constraints.return_origin = self._clean_place(text)
            elif state.status == "waiting_for_return_destination":
                if re.search(r"\b(same|wahi)\b", lower) and constraints.origin:
                    constraints.return_destination = constraints.origin
                elif not location_intent:
                    constraints.return_destination = self._clean_place(text)
            elif state.status == "waiting_for_return_date":
                if not date_value and not constraints.return_date:
                    constraints.return_date = text
            elif state.status == "waiting_for_return_time":
                if simple_time and not constraints.return_time:
                    constraints.return_time = simple_time.group(1).strip()

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

    def ask_knowledge(self, query: str, top_k: int = 4) -> tuple[str, list[Citation]]:
        """Standalone RAG Q&A: retrieve policy chunks and return a concise,
        grounded answer plus its citations.

        Powers the home "Ask a question" panel and reuses the same concise
        summariser as the chat's policy branch, so answers stay short and cited.
        """
        results = self.registry.retriever.search_knowledge(query, None, top_k)
        items = [item.model_dump(mode="json") for item in results]
        return self._policy_answer(items, query), self._citations(items)

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        # Embeddings are L2-normalized (both backends), so cosine == dot product.
        return sum(x * y for x, y in zip(a, b))

    def _policy_answer(self, results: list[dict[str, Any]], query: str) -> str:
        """A short, direct answer distilled from the retrieved policy chunks.

        Rather than dumping whole passages (a wall of text), split the top
        chunks into sentences and keep the two most relevant to the question —
        ranked by the same semantic embedder used for retrieval. General for any
        policy topic; nothing about the query or answer is hardcoded.
        """
        if not results:
            return (
                "I could not find that in the local policy knowledge base. "
                "For current operator rules, verify with the operator directly."
            )
        seen: set[str] = set()
        sentences: list[str] = []
        for item in results[:3]:
            for raw in re.split(r"(?<=[.!?])\s+", (item.get("text") or "").strip()):
                sentence = raw.strip()
                key = sentence.lower()
                if len(sentence) >= 30 and key not in seen:
                    seen.add(key)
                    sentences.append(sentence)
        if not sentences:
            return (results[0].get("text") or "")[:300].strip()

        embedder = self.registry.retriever.store.embedder
        query_vec = embedder.encode([query])[0]
        sentence_vecs = embedder.encode(sentences)
        ranked = sorted(
            range(len(sentences)),
            key=lambda i: self._cosine(query_vec, sentence_vecs[i]),
            reverse=True,
        )
        # Keep the two best sentences but restore original order so it reads
        # naturally; if those two are already long, one sentence is enough.
        best = sorted(ranked[:2])
        answer = " ".join(sentences[i] for i in best)
        if len(answer) > 420:
            answer = sentences[ranked[0]]
        return answer

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
    def _parse_date_expr(raw: str, base: date) -> date | None:
        """Parse a user-supplied date: ISO, dd/mm/yyyy, '15 July', 'tomorrow'…"""
        value = (raw or "").strip().lower()
        if not value:
            return None
        if value in {"today", "aaj"}:
            return base
        if value in {"tomorrow", "kal"}:
            return base + timedelta(days=1)
        if value in {"day after tomorrow", "parso"}:
            return base + timedelta(days=2)
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
        match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](20\d{2})", value)
        if match:
            try:
                return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
            except ValueError:
                return None
        cleaned = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", r"\1", value)
        cleaned = re.sub(r"[,.]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        for pattern in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(cleaned, pattern).date()
            except ValueError:
                continue
        for pattern in ("%d %B", "%d %b", "%B %d", "%b %d"):
            try:
                # Parse against the current year explicitly to avoid the
                # ambiguous no-year default (and Feb 29 failures).
                parsed = datetime.strptime(
                    f"{cleaned} {base.year}", f"{pattern} %Y"
                ).date()
            except ValueError:
                continue
            # A month/day with no year means the next such date, not last year's.
            return parsed if parsed >= base else parsed.replace(year=base.year + 1)
        return None

    @staticmethod
    def _client_base(request: ChatMessageRequest) -> datetime:
        try:
            tz = ZoneInfo(request.timezone) if request.timezone else timezone.utc
        except (KeyError, ValueError):
            tz = timezone.utc
        return (request.client_time or datetime.now(timezone.utc)).astimezone(tz)

    @staticmethod
    def _resolved_start(state: ConversationState, request: ChatMessageRequest) -> str | None:
        raw_date = state.constraints.start_date
        raw_time = state.constraints.start_time
        if not raw_date or not raw_time:
            return None
        # "9 AM" means 9 AM on the user's clock: resolve dates and stamp the
        # result in the client's timezone, not the server's UTC.
        base = ConversationAgent._client_base(request)
        resolved_date = ConversationAgent._parse_date_expr(raw_date, base.date())
        if resolved_date is None:
            return None
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
        constraints = state.constraints
        start_at = self._resolved_start(state, request)
        if start_at is None:
            base = self._client_base(request)
            if constraints.start_date and self._parse_date_expr(
                constraints.start_date, base.date()
            ) is None:
                constraints.start_date = None
                state.status = "waiting_for_start_date"
                return (
                    "I couldn't understand that date. What date would you like "
                    "to start? For example 2026-07-20, 20/07/2026, or 20 July.",
                    [],
                )
            state.constraints.start_time = None
            state.status = "waiting_for_start_time"
            return "Please enter a valid start time, for example 9:30 AM.", []
        goal = " ".join(turn.content for turn in state.turns[-8:] if turn.role == "user")
        if constraints.return_required and (
            constraints.return_origin or constraints.return_date
        ):
            # Keep the collected return-journey slots attached to the goal so
            # they survive even when the original message scrolls out of the
            # recent-turns window.
            goal += (
                f" Return journey from {constraints.return_origin or constraints.destination}"
                f" to {constraints.return_destination or constraints.origin}"
                + (f" on {constraints.return_date}" if constraints.return_date else "")
                + (f" at {constraints.return_time}" if constraints.return_time else "")
                + "."
            )
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
            answer = self._policy_answer(items, request.message)

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
            # Shared device coordinates resolve to a real place name before any
            # conversational handling, so the origin reads as e.g.
            # "Navrangpura, Ahmedabad" everywhere — never "Current location".
            located_name: str | None = None
            if (
                state.constraints.origin is None
                and request.current_lat is not None
                and request.current_lng is not None
                and (
                    re.search(r"\b(current|my location|here)\b", lower)
                    or state.status
                    in {
                        "awaiting_origin_choice",
                        "waiting_for_location_permission",
                        "waiting_for_origin",
                    }
                )
            ):
                located_name = self._resolve_current_location(request)
                state.constraints.origin = located_name
                state.constraints.origin_lat = request.current_lat
                state.constraints.origin_lng = request.current_lng

            # Primary brain: the LLM wrapper extracts the trip variables and
            # asks for the next missing one. It returns answer=None when the
            # provider is unavailable/unusable, in which case the deterministic
            # controller below takes over (also used offline and in tests).
            llm_answer, llm_actions, llm_mode = self._collect_intent_llm(
                state, request, trace, hinglish
            )
            if llm_answer is not None:
                answer = llm_answer
                suggested_actions.extend(llm_actions)
                mode = llm_mode or "llm"

            # Destination pin-pointing runs before the rest of the intent flow
            # and regardless of whether the LLM wrapper or the deterministic
            # controller produced the answer above. A broad destination (a whole
            # country/state/city) is narrowed to a specific place before we move
            # on to the origin, dates, or planning — so an LLM turn that accepted
            # "Gujarat" and jumped ahead to the origin/date still gets
            # interrupted to pin down where in Gujarat. classify_place() is
            # geocoder-backed and cached, so this works for any region worldwide
            # and returns None (no question) once the place is specific enough or
            # the user has accepted it.
            in_intent_phase = state.status in {
                "collecting_intent",
                "awaiting_origin_choice",
                "waiting_for_location_permission",
                "waiting_for_origin",
                "waiting_for_destination",
                "waiting_for_start_date",
                "waiting_for_start_time",
                "waiting_for_return",
                "waiting_for_return_origin",
                "waiting_for_return_destination",
                "waiting_for_return_date",
                "waiting_for_return_time",
            }
            narrowing_question = (
                self._place_narrowing_question(state, request.message, hinglish)
                if state.constraints.destination and in_intent_phase
                else None
            )
            narrowing_slot_status = "waiting_for_destination"
            broad_place = state.constraints.destination
            # Once the onward destination is settled, pin-point the return
            # destination (the trip's final endpoint) the same way.
            if (
                narrowing_question is None
                and state.constraints.return_destination
                and in_intent_phase
            ):
                return_question = self._place_narrowing_question(
                    state,
                    request.message,
                    hinglish,
                    place_field="return_destination",
                    prompted_field="return_narrowing_prompted_for",
                    pinned_field="return_destination_pinned",
                    en_verb="should the return journey end",
                    hi_verb="return khatam hogi",
                )
                if return_question:
                    narrowing_question = return_question
                    narrowing_slot_status = "waiting_for_return_destination"
                    broad_place = state.constraints.return_destination
            if narrowing_question:
                state.status = narrowing_slot_status
                answer = narrowing_question
                # We are asking about a destination now, so any origin or
                # location quick-replies from the LLM step no longer apply.
                suggested_actions = [
                    SuggestedAction(
                        id="keep_broad_destination",
                        label=f"Just {broad_place}",
                        message=f"Just {broad_place} is fine",
                    )
                ]

            is_travel = answer is None and (
                self._contains_any(lower, TRAVEL_TERMS)
                or state.status.startswith("waiting_for_")
                or state.status in {"awaiting_origin_choice", "choosing_legs"}
                or state.constraints.origin is not None
                or state.constraints.destination is not None
            )
            # Narrowing may restore a clobbered slot, so read these afterwards.
            origin = state.constraints.origin
            destination = state.constraints.destination
            if is_travel and not origin:
                wants_current = bool(re.search(r"\b(current|my location|here)\b", lower))
                wants_manual = bool(re.search(r"\b(manual|enter|type)\b", lower))
                # Note: "use current location" WITH coordinates never reaches
                # here — the coordinates are resolved to a real place name (and
                # stored as the origin) before the conversational handling.
                if wants_current:
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
            elif (
                is_travel and origin and destination
                and state.constraints.return_required
                and not state.constraints.return_origin
            ):
                state.status = "waiting_for_return_origin"
                answer = (
                    f"Return journey kahan se start hogi? Zaroori nahi ki {destination} se ho."
                    if hinglish
                    else (
                        f"Where will your return journey start? It doesn't have "
                        f"to be {destination} — tell me the starting place."
                    )
                )
                suggested_actions.append(
                    SuggestedAction(
                        id="return_origin_same",
                        label=f"Same as {destination}",
                        message=f"Same as {destination}",
                    )
                )
            elif (
                is_travel and origin and destination
                and state.constraints.return_required
                and not state.constraints.return_destination
            ):
                state.status = "waiting_for_return_destination"
                answer = (
                    f"Return journey kahan khatam hogi? Zaroori nahi ki {origin} ho."
                    if hinglish
                    else (
                        f"And where should the return journey end? It doesn't "
                        f"have to be {origin}."
                    )
                )
                suggested_actions.append(
                    SuggestedAction(
                        id="return_destination_same",
                        label=f"Same as {origin}",
                        message=f"Same as {origin}",
                    )
                )
            elif (
                is_travel and origin and destination
                and state.constraints.return_required
                and not state.constraints.return_date
            ):
                state.status = "waiting_for_return_date"
                answer = "What date is the return journey?"
            elif (
                is_travel and origin and destination
                and state.constraints.return_required
                and not state.constraints.return_time
            ):
                state.status = "waiting_for_return_time"
                answer = "What time would you like to start the return journey?"
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
            elif answer is None and re.search(r"\b(hi|hello|hey|namaste)\b", lower):
                answer = "Hi, where are you heading today?"

            # Acknowledge a freshly shared location with its resolved place
            # name so the user sees where the journey actually starts.
            if located_name and answer:
                prefix = (
                    f"Location mil gayi — {located_name} se start karenge."
                    if hinglish
                    else f"Got it — starting from {located_name}."
                )
                answer = f"{prefix} {answer}"

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
