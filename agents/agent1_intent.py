"""Agent 1 — Intent & Preference Agent.

Parses natural-language mobility goals into structured GoalContext,
loads learned user preferences, and records missing fields for HITL.

A deterministic rule-based parser always runs and is fully sufficient offline.
When Gemini is configured (GEMINI_API_KEY), an optional LLM pass enriches the
result — filling fields the rules missed — without changing the public
contract or removing the deterministic fallback.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from agents.user_memory import UserMemoryStore
from api.schemas import GoalContext, IntentResult, UserPreferences
from tools.llm import extract_json, gemini_enabled, generate_with_tools
from tools.maps_api import geocode as _geocode
from tools.places_india import resolve_place_name as _resolve_place_name


# ---------------------------------------------------------------------------
# Tools exposed to Gemini via function calling (Agent 1).
#
# These are plain module-level callables so the SDK can derive each
# function-declaration schema from the signature + docstring. They wrap the
# existing geocoding/catalog helpers and trim results to a JSON-safe subset.
# ---------------------------------------------------------------------------

_PLACE_FIELDS = ("name", "address", "city", "state", "lat", "lng", "place_type", "source")


def _trim_place(place: dict[str, Any]) -> dict[str, Any]:
    """Keep only JSON-safe, model-relevant fields from a place dict."""
    return {k: place.get(k) for k in _PLACE_FIELDS if place.get(k) is not None}


def resolve_india_place(name: str) -> dict[str, Any]:
    """Resolve an Indian place name against the offline curated catalog.

    Use this first for any city, locality, landmark, or airport in India.
    Returns the canonical name, city, state, coordinates and place_type when
    the place is in the catalog.

    Args:
        name: A place, locality, city, landmark, or airport name in India.
    """
    place = _resolve_place_name(name)
    if not place:
        return {"found": False, "query": name}
    return {"found": True, **_trim_place(place)}


def geocode_place(query: str) -> dict[str, Any]:
    """Geocode a free-text place to coordinates and a canonical address.

    Tries the curated India catalog, then free OpenStreetMap Nominatim, then
    Google (if configured). Use this when resolve_india_place did not find the
    place.

    Args:
        query: Free-text place description to geocode.
    """
    place = _geocode(query)
    if not place:
        return {"found": False, "query": query}
    return {"found": True, **_trim_place(place)}


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
            # Patterns: "to X", "at X", "reach X", "go to X", "visit X", etc.
            # Capture only the run of Title-Case words after the trigger (place
            # names are capitalized) so trailing lowercase sentence words like
            # "for a meeting tomorrow" don't get swept into the destination.
            # "from X" is handled separately as the origin, so exclude it here.
            # (?i:...) makes only the trigger words case-insensitive (so a
            # sentence-initial "To"/"Reach" still matches) while the captured
            # place name stays Title-Case-only.
            m = re.search(
                r"(?i:\b(?:to|at|towards?|for|reach(?:ing)?|"
                r"visit(?:ing)?|headed|heading))\s+"
                r"([A-Z][A-Za-z0-9&'-]*(?:\s+[A-Z][A-Za-z0-9&'-]*)*)",
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
            # 1. Explicit origin markers: "from X", "leaving X", "starting from
            #    X", "currently in/at X", "I'm in/at/near X", "based in X".
            m = re.search(
                r"(?i:\b(?:from|leaving|starting\s+from|start\s+from|"
                r"currently\s+(?:in|at)|based\s+(?:in|at)|"
                r"i'm\s+(?:in|at|near)|i\s+am\s+(?:in|at|near)))\s+"
                r"([A-Z][A-Za-z0-9&'-]*(?:\s+[A-Z][A-Za-z0-9&'-]*)*)",
                raw,
            )
            if m:
                origin = m.group(1).strip(" .,")
            if not origin:
                # 2. "A to B" phrasing without an explicit "from": the Title-Case
                #    place immediately before " to <Place>" is the origin.
                m2 = re.search(
                    r"\b([A-Z][A-Za-z0-9&'-]*(?:\s+[A-Z][A-Za-z0-9&'-]*)*)"
                    r"(?i:\s+to\s+)"
                    r"[A-Z][A-Za-z0-9&'-]*",
                    raw,
                )
                if m2:
                    candidate = m2.group(1).strip(" .,")
                    # Don't mistake the destination (or a leading verb) for origin.
                    if candidate.lower() != (dest or "").lower():
                        origin = candidate
            if not origin and prefs.home_label:
                origin = prefs.home_label
                reasoning.append(f"Using learned home as origin: {origin}.")
        if origin:
            reasoning.append(f"Origin hint: {origin}.")
        else:
            reasoning.append("No origin found in text; will ask the user.")

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

        # --- Optional LLM enrichment (fills gaps only; never overrides rules) ---
        llm_used = False
        resolved_meta: dict[str, Any] = {}
        if use_llm and raw and gemini_enabled():
            llm = self._llm_extract(raw)
            if llm:
                llm_used = True
                tool_calls = llm.pop("_tool_calls", [])
                reasoning.append("Gemini enrichment applied to fill missing fields.")
                if tool_calls:
                    reasoning.append(
                        "Gemini invoked tools: " + ", ".join(tool_calls) + "."
                    )
                    # Only trust resolved coordinates when a tool actually ran.
                    if isinstance(llm.get("origin_resolved"), dict):
                        resolved_meta["origin_resolved"] = llm["origin_resolved"]
                    if isinstance(llm.get("destination_resolved"), dict):
                        resolved_meta["destination_resolved"] = llm["destination_resolved"]
                if not dest and llm.get("destination"):
                    candidate = self._sanitize_llm_place(str(llm["destination"]), raw)
                    if candidate:
                        dest = candidate
                        reasoning.append(f"LLM destination: {dest}.")
                    else:
                        reasoning.append(
                            f"Discarded LLM destination guess "
                            f"{llm['destination']!r}; not grounded in user text."
                        )
                if not origin and llm.get("origin"):
                    candidate = self._sanitize_llm_place(str(llm["origin"]), raw)
                    if candidate:
                        origin = candidate
                        reasoning.append(f"LLM origin: {origin}.")
                    else:
                        reasoning.append(
                            f"Discarded LLM origin guess "
                            f"{llm['origin']!r}; not grounded in user text."
                        )
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
                **resolved_meta,
            },
        )

        missing: list[str] = []
        if not dest and not destination_hint:
            missing.append("destination")
        if not origin and not origin_hint and prefs.home_label is None:
            missing.append("origin")

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
            reasoning=reasoning,
            missing_fields=missing,
        )

    # ------------------------------------------------------------------
    # Optional LLM enrichment
    # ------------------------------------------------------------------

    def _llm_extract(self, text: str) -> Optional[dict[str, Any]]:
        """Ask Gemini to extract structured mobility fields, calling the
        geocoding/catalog tools to ground origin and destination.

        Returns the parsed JSON dict (optionally carrying a ``_tool_calls``
        list of tool names invoked), or ``None`` on any failure so the
        deterministic parse stands alone.
        """
        system = (
            "You extract structured travel intent from a user's message about "
            "commuting within India, and you ground the origin and destination "
            "using the provided tools.\n"
            "Rules:\n"
            "- Use the user's own wording for place names; never invent a more "
            "specific mall, building, or business the user did not name.\n"
            "- When the user names an origin or destination, call "
            "resolve_india_place first; if it returns found=false, call "
            "geocode_place.\n"
            "- After resolving, reply with a SINGLE JSON object only, no prose."
        )
        prompt = (
            f"Message: {text!r}\n\n"
            "Extract these fields (use null when unknown):\n"
            "  origin: string | null (starting place, in the user's own "
            "wording)\n"
            "  destination: string | null (where they need to go, user's "
            "wording)\n"
            "  purpose: one of [interview, meeting, flight_catch, tourism, "
            "medical, education, commute, general] | null\n"
            "  return_required: boolean | null (do they need a return trip)\n"
            "  luggage_count: integer | null (number of bags/suitcases)\n"
            "  required_buffer_minutes: integer | null (how early they must "
            "arrive, in minutes)\n"
            "  origin_resolved / destination_resolved: object | null — when you "
            "resolved a place via a tool, include {name, lat, lng, city, "
            "state, place_type} from the tool result; otherwise null.\n\n"
            'Respond with JSON like {"origin": ..., "destination": ..., '
            '"purpose": ..., "return_required": ..., "luggage_count": ..., '
            '"required_buffer_minutes": ..., "origin_resolved": ..., '
            '"destination_resolved": ...}.'
        )
        result = generate_with_tools(
            prompt,
            system=system,
            tools=[resolve_india_place, geocode_place],
            temperature=0.1,
        )
        if not result:
            return None
        data = extract_json(result.get("text", ""))
        if data is None:
            return None
        if result.get("tool_calls"):
            data["_tool_calls"] = result["tool_calls"]
        return data

    @staticmethod
    def _sanitize_llm_place(value: str, raw_text: str) -> Optional[str]:
        """Guard against the LLM 'autocompleting' a plain place name into a
        specific business/landmark the user never mentioned (e.g. turning
        "Koramangala" into "Nexus Koramangala"). Only trust wording that
        actually appears in the user's own text.
        """
        val = value.strip()
        if not val:
            return None
        raw_lower = raw_text.lower()
        if val.lower() in raw_lower:
            return val
        val_words = val.split()
        kept = [w for w in val_words if w.lower() in raw_lower]
        if not kept:
            return None
        if len(kept) == len(val_words):
            return val
        # Partial overlap: the LLM likely bolted an extra business/landmark
        # name onto a real place the user mentioned. Rebuild from the
        # user's own text instead of trusting the LLM's invented words.
        raw_words = re.findall(r"[A-Za-z0-9]+", raw_text)
        kept_lower = {w.lower() for w in kept}
        matched_raw = [w for w in raw_words if w.lower() in kept_lower]
        return " ".join(matched_raw) if matched_raw else None
