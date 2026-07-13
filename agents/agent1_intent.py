"""Agent 1 — Intent & Preference Agent.

Parses natural-language mobility goals into structured GoalContext,
loads learned user preferences, and records missing fields for HITL.

A deterministic rule-based parser always runs and is fully sufficient offline.
When Gemini is configured (GEMINI_API_KEY), an optional LLM pass enriches the
result — filling fields the rules missed and boosting confidence — without
changing the public contract or removing the deterministic fallback.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from agents.user_memory import UserMemoryStore
from api.schemas import GoalContext, IntentResult, UserPreferences
from tools.llm import gemini_enabled, generate_json


class IntentAgent:
    """Extract mobility intent and merge with learned preferences."""

    def __init__(self, memory: Optional[UserMemoryStore] = None) -> None:
        self.memory = memory or UserMemoryStore()

    def get_preferences(self, user_id: str) -> UserPreferences:
        return self.memory.get_preferences(user_id)

    def parse_intent(
        self,
        user_id: str,
        text: str,
        *,
        origin_hint: Optional[str] = None,
        destination_hint: Optional[str] = None,
        appointment_time: Optional[datetime] = None,
        return_required: Optional[bool] = None,
        luggage_count: Optional[int] = None,
        required_buffer_minutes: Optional[int] = None,
        use_llm: bool = True,
    ) -> IntentResult:
        """Parse free-text goal into IntentResult + GoalContext.

        The deterministic parser always runs. If ``use_llm`` is set and Gemini
        is configured, an LLM pass fills any gaps the rules left open.
        """
        prefs = self.memory.get_preferences(user_id)
        reasoning: list[str] = []
        raw = (text or "").strip()
        lower = raw.lower()

        reasoning.append(f"Received goal text ({len(raw)} chars).")
        reasoning.append(
            f"Loaded profile for {user_id}: "
            f"{prefs.interaction_count} prior interactions, "
            f"preferred_modes={prefs.preferred_modes}."
        )

        # --- Purpose ---
        purpose = None
        purpose_map = {
            "interview": ["interview", "hiring", "campus placement"],
            "meeting": ["meeting", "client", "office visit"],
            "flight_catch": ["catch a flight", "airport drop"],
            "tourism": ["tourist", "sightseeing", "vacation", "holiday"],
            "medical": ["hospital", "doctor", "clinic", "appointment with"],
            "education": ["exam", "college", "university", "class"],
            "commute": ["office", "work", "daily commute"],
        }
        for purp, keys in purpose_map.items():
            if any(k in lower for k in keys):
                purpose = purp
                break
        if purpose:
            reasoning.append(f"Inferred purpose: {purpose}.")
        else:
            purpose = "general"
            reasoning.append("Purpose defaulted to general.")

        # --- Destination extraction ---
        dest = destination_hint
        if not dest:
            # Patterns: "at X", "to X", "in X"
            m = re.search(
                r"\b(?:at|to|towards|for)\s+([A-Z][A-Za-z0-9 .&'-]{2,40})",
                raw,
            )
            if m:
                dest = m.group(1).strip(" .,")
            # Known landmarks
            known = [
                "jio institute",
                "iit bombay",
                "isb hyderabad",
                "iisc bengaluru",
                "india gate",
                "gateway of india",
                "statue of unity",
                "taj mahal",
                "mumbai airport",
                "ahmedabad airport",
                "delhi airport",
            ]
            for k in known:
                if k in lower:
                    dest = k.title() if k != "jio institute" else "Jio Institute"
                    if k == "jio institute":
                        dest = "Jio Institute"
                    break
            # City names
            cities = [
                "navi mumbai",
                "ahmedabad",
                "mumbai",
                "delhi",
                "bengaluru",
                "bangalore",
                "hyderabad",
                "pune",
                "chennai",
                "kolkata",
                "jaipur",
                "kochi",
                "goa",
            ]
            if not dest:
                for c in cities:
                    if c in lower:
                        dest = c.title() if c != "navi mumbai" else "Navi Mumbai"
                        if c == "bangalore":
                            dest = "Bengaluru"
                        break
        if dest:
            reasoning.append(f"Destination hint: {dest}.")
        else:
            reasoning.append("No destination found in text; UI/map input may supply it.")

        # Navi Mumbai + Jio special case
        if dest and "jio" in dest.lower():
            dest = "Jio Institute"
        if "jio institute" in lower and "navi" in lower:
            dest = "Jio Institute"
            reasoning.append("Resolved 'Jio Institute in Navi Mumbai' → Jio Institute.")

        # --- Origin ---
        origin = origin_hint
        if not origin:
            m = re.search(
                r"\b(?:from|leaving)\s+([A-Z][A-Za-z0-9 .&'-]{2,40})",
                raw,
            )
            if m:
                origin = m.group(1).strip(" .,")
            elif prefs.home_label:
                origin = prefs.home_label
                reasoning.append(f"Using learned home as origin: {origin}.")
        if origin:
            reasoning.append(f"Origin hint: {origin}.")

        # --- Return ---
        ret = return_required
        if ret is None:
            ret = any(
                p in lower
                for p in (
                    "return",
                    "round trip",
                    "come back",
                    "same evening",
                    "same day return",
                    "return journey",
                )
            )
        reasoning.append(f"Return required: {ret}.")

        # --- Luggage ---
        luggage = luggage_count
        if luggage is None:
            m = re.search(r"(\d+)\s*(suitcase|bag|luggage|check[- ]?in)", lower)
            if m:
                luggage = int(m.group(1))
            elif "suitcase" in lower or "luggage" in lower:
                luggage = 1
            else:
                luggage = prefs.luggage_default
        reasoning.append(f"Luggage count: {luggage}.")

        # --- Buffer ---
        buffer = required_buffer_minutes
        if buffer is None:
            m = re.search(
                r"(?:at least\s+)?(\d+)\s*(hour|hr|minute|min)s?\s*(?:early|before|buffer)",
                lower,
            )
            if m:
                val = int(m.group(1))
                unit = m.group(2)
                buffer = val * 60 if unit.startswith("hour") or unit == "hr" else val
            elif "early" in lower:
                buffer = 60
            else:
                buffer = prefs.default_buffer_minutes
        reasoning.append(f"Required buffer: {buffer} minutes.")

        # --- Appointment time ---
        appt = appointment_time
        if appt is None:
            now = datetime.now(timezone.utc)
            if "tomorrow" in lower:
                appt = (now + timedelta(days=1)).replace(
                    hour=10, minute=0, second=0, microsecond=0
                )
                reasoning.append("Appointment defaulted to tomorrow 10:00 UTC.")
            elif "today" in lower:
                appt = now.replace(hour=18, minute=0, second=0, microsecond=0)
                if appt < now:
                    appt = now + timedelta(hours=3)
                reasoning.append("Appointment set for today evening / +3h.")
            else:
                # Look for HH:MM
                tm = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", lower)
                if tm:
                    h, mi = int(tm.group(1)), int(tm.group(2))
                    ampm = tm.group(3)
                    if ampm == "pm" and h < 12:
                        h += 12
                    if ampm == "am" and h == 12:
                        h = 0
                    appt = now.replace(hour=h, minute=mi, second=0, microsecond=0)
                    if appt < now:
                        appt += timedelta(days=1)
                    reasoning.append(f"Parsed clock time → {appt.isoformat()}.")
                else:
                    appt = now + timedelta(days=1)
                    appt = appt.replace(hour=10, minute=0, second=0, microsecond=0)
                    reasoning.append("No time found; default appointment tomorrow 10:00 UTC.")

        # Preference signals in text
        if any(w in lower for w in ("cheap", "budget", "lowest fare", "save money")):
            prefs.prefer_cheapest = True
            prefs.prefer_fastest = False
            reasoning.append("User signal: prefer cheapest.")
        if any(w in lower for w in ("fastest", "asap", "urgent", "quickest")):
            prefs.prefer_fastest = True
            reasoning.append("User signal: prefer fastest.")
        if any(w in lower for w in ("comfort", "business class", "premium")):
            prefs.prefer_comfort = True
            reasoning.append("User signal: prefer comfort.")
        if any(w in lower for w in ("eco", "green", "low emission", "sustainable")):
            prefs.prefer_low_emission = True
            reasoning.append("User signal: prefer low emission.")

        # --- Optional LLM enrichment (fills gaps only; never overrides rules) ---
        llm_used = False
        if use_llm and raw and gemini_enabled():
            llm = self._llm_extract(raw)
            if llm:
                llm_used = True
                reasoning.append("Gemini enrichment applied to fill missing fields.")
                if not dest and llm.get("destination"):
                    dest = str(llm["destination"]).strip()
                    reasoning.append(f"LLM destination: {dest}.")
                if not origin and llm.get("origin"):
                    origin = str(llm["origin"]).strip()
                    reasoning.append(f"LLM origin: {origin}.")
                if purpose == "general" and llm.get("purpose"):
                    purpose = str(llm["purpose"]).strip().lower().replace(" ", "_")
                    reasoning.append(f"LLM purpose: {purpose}.")
                if return_required is None and isinstance(llm.get("return_required"), bool):
                    ret = llm["return_required"]
                    reasoning.append(f"LLM return_required: {ret}.")
                if luggage_count is None and isinstance(llm.get("luggage_count"), int):
                    luggage = llm["luggage_count"]
                    reasoning.append(f"LLM luggage_count: {luggage}.")
                if required_buffer_minutes is None and isinstance(
                    llm.get("required_buffer_minutes"), int
                ):
                    buffer = llm["required_buffer_minutes"]
                    reasoning.append(f"LLM buffer: {buffer} min.")

        goal = GoalContext(
            goal_statement=raw or f"Travel to {dest or 'destination'}",
            purpose=purpose,
            destination_name=dest,
            destination_address=None,
            appointment_time=appt,
            return_required=bool(ret),
            luggage_count=int(luggage or 0),
            required_buffer_minutes=int(buffer or 0),
            metadata={
                "origin_hint": origin,
                "parsed_by": "IntentAgent.v1+gemini" if llm_used else "IntentAgent.v1",
                "llm_used": llm_used,
            },
        )

        missing: list[str] = []
        if not dest and not destination_hint:
            missing.append("destination")
        if not origin and not origin_hint and prefs.home_label is None:
            missing.append("origin")

        confidence = 0.55
        if dest:
            confidence += 0.2
        if origin:
            confidence += 0.1
        if purpose != "general":
            confidence += 0.1
        if llm_used:
            confidence += 0.05
        confidence = min(0.97, confidence)

        self.memory.record_event(
            user_id,
            "intent_parse",
            {
                "text": raw[:500],
                "destination": dest,
                "origin": origin,
                "purpose": purpose,
            },
        )
        # Persist soft preference updates from this parse
        self.memory.save_preferences(prefs)

        return IntentResult(
            user_id=user_id,
            raw_text=raw,
            goal_context=goal,
            origin_hint=origin,
            destination_hint=dest,
            preferences=prefs,
            confidence=confidence,
            reasoning=reasoning,
            missing_fields=missing,
        )

    # ------------------------------------------------------------------
    # Optional LLM enrichment
    # ------------------------------------------------------------------

    def _llm_extract(self, text: str) -> Optional[dict[str, Any]]:
        """Ask Gemini to extract structured mobility fields as JSON.

        Returns ``None`` on any failure so the deterministic parse stands alone.
        """
        system = (
            "You extract structured travel intent from a user's message about "
            "commuting within India. Reply with a single JSON object only."
        )
        prompt = (
            "Extract these fields from the message (use null when unknown):\n"
            "  origin: string | null (starting place)\n"
            "  destination: string | null (where they need to go)\n"
            "  purpose: one of [interview, meeting, flight_catch, tourism, "
            "medical, education, commute, general] | null\n"
            "  return_required: boolean | null (do they need a return trip)\n"
            "  luggage_count: integer | null (number of bags/suitcases)\n"
            "  required_buffer_minutes: integer | null (how early they must "
            "arrive, in minutes)\n\n"
            f"Message: {text!r}\n"
            'Respond with JSON like {"origin": ..., "destination": ..., '
            '"purpose": ..., "return_required": ..., "luggage_count": ..., '
            '"required_buffer_minutes": ...}.'
        )
        return generate_json(prompt, system=system, temperature=0.1)
