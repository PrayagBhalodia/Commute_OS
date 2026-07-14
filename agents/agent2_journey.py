"""Agent 2 — Journey Composition & Scoring Agent.

Composes multi-leg itineraries from origin → destination using maps tools
and mock transport availability. Scores options with user preferences.
No LLM required.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from api.schemas import (
    GoalContext,
    ItineraryOption,
    LegOption,
    PlaceInfo,
    TransportMode,
    UserPreferences,
)
from tools import mock_cab_api, mock_flight_api, mock_transit_api
from tools.llm import gemini_enabled, generate_text
from tools.maps_api import directions_summary, distance_matrix, resolve_origin_destination
from tools.places_india import nearest_airport


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _place_info(d: dict[str, Any]) -> PlaceInfo:
    return PlaceInfo(
        place_id=str(d.get("place_id", "unknown")),
        name=str(d.get("name", "Unknown")),
        address=str(d.get("address", d.get("name", ""))),
        city=d.get("city"),
        state=d.get("state"),
        lat=float(d["lat"]),
        lng=float(d["lng"]),
        place_type=str(d.get("place_type", "city")),
        metadata={k: v for k, v in d.items() if k not in {
            "place_id", "name", "address", "city", "state", "lat", "lng", "place_type"
        }},
    )


def _latlng(point: Any) -> Optional[tuple[float, float]]:
    """Best-effort (lat, lng) from a PlaceInfo or a place dict."""
    if point is None:
        return None
    if isinstance(point, dict):
        if point.get("lat") is None or point.get("lng") is None:
            return None
        return float(point["lat"]), float(point["lng"])
    lat, lng = getattr(point, "lat", None), getattr(point, "lng", None)
    if lat is None or lng is None:
        return None
    return float(lat), float(lng)


def _geo(frm: Any, to: Any) -> dict[str, float]:
    """Leg endpoint coordinates for map rendering. Missing points are omitted."""
    meta: dict[str, float] = {}
    a, b = _latlng(frm), _latlng(to)
    if a:
        meta["from_lat"], meta["from_lng"] = a
    if b:
        meta["to_lat"], meta["to_lng"] = b
    return meta


class JourneyCompositionAgent:
    """Compose and score end-to-end multi-modal itineraries."""

    def compose(
        self,
        *,
        user_id: str,
        trip_id: str,
        goal: GoalContext,
        preferences: UserPreferences,
        origin_text: Optional[str] = None,
        destination_text: Optional[str] = None,
        origin_lat: Optional[float] = None,
        origin_lng: Optional[float] = None,
        destination_lat: Optional[float] = None,
        destination_lng: Optional[float] = None,
        max_options: int = 3,
        use_llm: bool = True,
    ) -> tuple[PlaceInfo, PlaceInfo, float, list[ItineraryOption], list[str]]:
        """Return origin, destination, distance_km, ranked itineraries, reasoning."""
        reasoning: list[str] = []

        dest_text = destination_text or goal.destination_name
        origin, destination, dist_km = resolve_origin_destination(
            origin_text=origin_text,
            destination_text=dest_text,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            destination_lat=destination_lat,
            destination_lng=destination_lng,
        )
        o = _place_info(origin)
        d = _place_info(destination)
        # Enrich goal destination address
        goal.destination_name = goal.destination_name or d.name
        goal.destination_address = d.address

        summary = directions_summary(origin, destination)
        reasoning.append(
            f"Resolved origin={o.name}, destination={d.name}, "
            f"distance≈{dist_km:.1f} km (maps source: {summary.get('source')})."
        )
        reasoning.append(
            f"Routing hints: same_city={summary['same_city']}, "
            f"flight={summary['suggest_flight']}, train={summary['suggest_train']}, "
            f"cab_only={summary['suggest_cab_only']}."
        )

        appointment = goal.appointment_time or (_utc_now() + timedelta(days=1))
        if appointment.tzinfo is None:
            appointment = appointment.replace(tzinfo=timezone.utc)
        buffer = goal.required_buffer_minutes or preferences.default_buffer_minutes
        arrive_by = appointment - timedelta(minutes=buffer)

        options: list[ItineraryOption] = []

        # Strategy A: cab-only (local)
        if summary["suggest_cab_only"] or dist_km < 120:
            opt = self._build_cab_only(
                trip_id, goal, o, d, origin, destination, arrive_by, "fast"
            )
            options.append(opt)
            reasoning.append(f"Composed cab-only option {opt.itinerary_id} ₹{opt.total_price:.0f}.")

        # Strategy B: flight hub-to-hub
        if summary["suggest_flight"] or dist_km > 200:
            opt = self._build_flight_chain(
                trip_id, goal, o, d, origin, destination, arrive_by, goal.luggage_count, "balanced"
            )
            if opt:
                options.append(opt)
                reasoning.append(
                    f"Composed flight chain {opt.itinerary_id} ₹{opt.total_price:.0f}."
                )

        # Strategy C: train + local
        if summary["suggest_train"] or (80 < dist_km <= 900):
            opt = self._build_train_chain(
                trip_id, goal, o, d, origin, destination, arrive_by, "economy"
            )
            if opt:
                options.append(opt)
                reasoning.append(
                    f"Composed train chain {opt.itinerary_id} ₹{opt.total_price:.0f}."
                )

        # Strategy D: comfort / premium flight variant
        if dist_km > 200 and len(options) < max_options + 1:
            opt = self._build_flight_chain(
                trip_id,
                goal,
                o,
                d,
                origin,
                destination,
                arrive_by,
                goal.luggage_count,
                "comfort",
                operator="Air India",
                cab_operator="Uber",
            )
            if opt:
                opt.explanation = "Premium comfort-oriented option (Air India + Uber)."
                options.append(opt)

        # Guarantee at least two options to compare. Short local hops often
        # yield only a cab-only route; synthesize a premium variant so the user
        # always has a genuine choice.
        if len(options) == 1:
            options.append(self._premium_variant(options[0]))
            reasoning.append(
                "Only one route was viable; added a premium comfort variant "
                "so at least two options are offered."
            )

        # Return legs if needed
        if goal.return_required:
            enriched: list[ItineraryOption] = []
            for opt in options:
                enriched.append(
                    self._append_return(opt, goal, o, d, origin, destination, appointment)
                )
            options = enriched
            reasoning.append("Appended same-day/evening return legs (return_required=True).")

        # Score & rank
        scored = [self._score(opt, preferences) for opt in options]
        scored.sort(key=lambda x: x.score, reverse=True)
        # Always surface at least two options for comparison when available.
        scored = scored[: max(2, max_options)]
        reasoning.append(
            "Ranked itineraries by preference-weighted score: "
            + ", ".join(f"{s.itinerary_id}={s.score:.2f}" for s in scored)
        )

        # Optional: let Gemini phrase a recommendation for the top option.
        if use_llm and scored and gemini_enabled():
            rec = self._llm_recommend(goal, preferences, scored)
            if rec:
                scored[0].explanation = rec
                scored[0].metadata = {**scored[0].metadata, "llm_recommended": True}
                reasoning.append("Gemini refined the top itinerary's explanation.")

        return o, d, dist_km, scored, reasoning

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    def _premium_variant(self, opt: ItineraryOption) -> ItineraryOption:
        """Clone an itinerary as an upgraded-comfort alternative — same route,
        premium operators, a bit pricier — so there are always >= 2 options.
        """
        premium_ops = {
            TransportMode.CAB: "Uber",
            TransportMode.FLIGHT: "Air India",
        }
        legs = [
            LegOption(
                leg_id=f"{lg.leg_id}-prem-{uuid.uuid4().hex[:4]}",
                mode=lg.mode,
                operator=premium_ops.get(lg.mode, lg.operator),
                origin=lg.origin,
                destination=lg.destination,
                departure=lg.departure,
                arrival=lg.arrival,
                price=round(lg.price * 1.25, 2),
                comfort_score=min(1.0, lg.comfort_score + 0.2),
                service_id=lg.service_id,
                metadata={**lg.metadata, "variant": "premium"},
            )
            for lg in opt.legs
        ]
        return ItineraryOption(
            itinerary_id=f"{opt.itinerary_id}-prem",
            trip_id=opt.trip_id,
            goal_context=opt.goal_context,
            legs=legs,
            total_price=round(sum(lg.price for lg in legs), 2),
            total_duration_minutes=opt.total_duration_minutes,
            score=0.0,
            explanation="Premium comfort variant — same route, upgraded operators.",
            metadata={**opt.metadata, "strategy": "premium_variant", "tag": "comfort"},
        )

    def _build_cab_only(
        self,
        trip_id: str,
        goal: GoalContext,
        o: PlaceInfo,
        d: PlaceInfo,
        origin: dict,
        destination: dict,
        arrive_by: datetime,
        tag: str,
    ) -> ItineraryOption:
        dm = distance_matrix(origin, destination, mode="driving")
        duration = max(20.0, float(dm["duration_minutes"]))
        quotes = mock_cab_api.get_cab_quotes(
            o.name, d.name, operator="Ola", luggage_count=goal.luggage_count,
            distance_km=dm["distance_km"],
            failure_rate=0.0, latency_seconds=0.0,
        )
        price = quotes[0]["amount"] if quotes else max(150.0, dm["distance_km"] * 18)
        dep = arrive_by - timedelta(minutes=duration)
        leg = LegOption(
            leg_id=f"leg-cab-{tag}-{uuid.uuid4().hex[:6]}",
            mode=TransportMode.CAB,
            operator="Ola",
            origin=o.name,
            destination=d.name,
            departure=dep,
            arrival=dep + timedelta(minutes=duration),
            price=round(price, 2),
            comfort_score=0.65,
            service_id="CAB-SVC-OLA",
            metadata={"duration_min": duration, **_geo(o, d)},
        )
        return ItineraryOption(
            itinerary_id=f"itin-cab-{tag}-{uuid.uuid4().hex[:6]}",
            trip_id=trip_id,
            goal_context=goal,
            legs=[leg],
            total_price=leg.price,
            total_duration_minutes=duration,
            score=0.0,
            explanation="Door-to-door cab — simplest local option.",
            metadata={"strategy": "cab_only", "tag": tag},
        )

    def _build_flight_chain(
        self,
        trip_id: str,
        goal: GoalContext,
        o: PlaceInfo,
        d: PlaceInfo,
        origin: dict,
        destination: dict,
        arrive_by: datetime,
        luggage: int,
        tag: str,
        operator: str = "IndiGo",
        cab_operator: str = "Ola",
    ) -> Optional[ItineraryOption]:
        o_apt = nearest_airport(origin)
        d_apt = nearest_airport(destination)
        if not o_apt or not d_apt:
            return None
        if o_apt["place_id"] == d_apt["place_id"] and distance_matrix(origin, destination)["distance_km"] < 150:
            return None

        # Leg times working backwards from arrive_by
        dm_last = distance_matrix(d_apt, destination, mode="driving")
        cab2_min = max(25.0, float(dm_last["duration_minutes"]))
        flt_dist = distance_matrix(o_apt, d_apt)["distance_km"]
        flight_min = 95.0 if flt_dist < 900 else 150.0
        dm_first = distance_matrix(origin, o_apt, mode="driving")
        cab1_min = max(25.0, float(dm_first["duration_minutes"]))

        arr_dest = arrive_by
        dep_cab2 = arr_dest - timedelta(minutes=cab2_min)
        arr_flight = dep_cab2 - timedelta(minutes=20)  # deplane buffer
        dep_flight = arr_flight - timedelta(minutes=flight_min)
        arr_cab1 = dep_flight - timedelta(minutes=90)  # airport buffer
        dep_cab1 = arr_cab1 - timedelta(minutes=cab1_min)

        q1 = mock_cab_api.get_cab_quotes(
            o.name, o_apt["name"], operator=cab_operator, luggage_count=luggage,
            distance_km=dm_first["distance_km"],
            failure_rate=0.0, latency_seconds=0.0,
        )
        qf = mock_flight_api.get_flight_quotes(
            o_apt["name"], d_apt["name"], operator=operator,
            distance_km=flt_dist,
            failure_rate=0.0, latency_seconds=0.0,
        )
        q2 = mock_cab_api.get_cab_quotes(
            d_apt["name"], d.name, operator=cab_operator, luggage_count=luggage,
            distance_km=dm_last["distance_km"],
            failure_rate=0.0, latency_seconds=0.0,
        )
        p1 = q1[0]["amount"] if q1 else 450.0
        pf = qf[0]["amount"] if qf else 4200.0
        if operator == "Air India":
            pf *= 1.15
        p2 = q2[0]["amount"] if q2 else 850.0

        legs = [
            LegOption(
                leg_id=f"leg-1-cab-{tag}-{uuid.uuid4().hex[:4]}",
                mode=TransportMode.CAB,
                operator=cab_operator,
                origin=o.name,
                destination=o_apt["name"],
                departure=dep_cab1,
                arrival=arr_cab1,
                price=round(p1, 2),
                comfort_score=0.7 if cab_operator == "Uber" else 0.65,
                metadata=_geo(o, o_apt),
            ),
            LegOption(
                leg_id=f"leg-2-flt-{tag}-{uuid.uuid4().hex[:4]}",
                mode=TransportMode.FLIGHT,
                operator=operator,
                origin=o_apt["name"],
                destination=d_apt["name"],
                departure=dep_flight,
                arrival=arr_flight,
                price=round(pf, 2),
                comfort_score=0.9 if operator == "Air India" else 0.8,
                service_id=f"FLT-{operator[:3].upper()}",
                metadata=_geo(o_apt, d_apt),
            ),
            LegOption(
                leg_id=f"leg-3-cab-{tag}-{uuid.uuid4().hex[:4]}",
                mode=TransportMode.CAB,
                operator=cab_operator if cab_operator == "Uber" else "Uber",
                origin=d_apt["name"],
                destination=d.name,
                departure=dep_cab2,
                arrival=arr_dest,
                price=round(p2, 2),
                comfort_score=0.75,
                metadata=_geo(d_apt, d),
            ),
        ]
        total_price = sum(lg.price for lg in legs)
        total_dur = (arr_dest - dep_cab1).total_seconds() / 60.0
        return ItineraryOption(
            itinerary_id=f"itin-flt-{tag}-{uuid.uuid4().hex[:6]}",
            trip_id=trip_id,
            goal_context=goal,
            legs=legs,
            total_price=round(total_price, 2),
            total_duration_minutes=round(total_dur, 1),
            score=0.0,
            explanation=(
                f"Multi-leg: cab → {operator} flight → cab. "
                f"Arrives {buffer_msg(goal)} before appointment."
            ),
            metadata={"strategy": "flight_chain", "tag": tag},
        )

    def _build_train_chain(
        self,
        trip_id: str,
        goal: GoalContext,
        o: PlaceInfo,
        d: PlaceInfo,
        origin: dict,
        destination: dict,
        arrive_by: datetime,
        tag: str,
    ) -> Optional[ItineraryOption]:
        dist = distance_matrix(origin, destination)["distance_km"]
        if dist < 60:
            return None
        train_hours = max(3.0, dist / 65.0)
        train_min = train_hours * 60
        cab_min = 40.0
        arr = arrive_by
        dep_cab2 = arr - timedelta(minutes=cab_min)
        arr_train = dep_cab2 - timedelta(minutes=15)
        dep_train = arr_train - timedelta(minutes=train_min)
        arr_cab1 = dep_train - timedelta(minutes=30)
        dep_cab1 = arr_cab1 - timedelta(minutes=cab_min)

        tq = mock_transit_api.get_transit_quotes(
            o.city or o.name, d.city or d.name, mode="train", operator="IRCTC",
            distance_km=dist,
            failure_rate=0.0, latency_seconds=0.0,
        )
        train_price = tq[0]["amount"] if tq else max(400.0, dist * 1.2)
        cab_price = 350.0

        legs = [
            LegOption(
                leg_id=f"leg-t1-{uuid.uuid4().hex[:4]}",
                mode=TransportMode.CAB,
                operator="Ola",
                origin=o.name,
                destination=f"{o.city or o.name} Station",
                departure=dep_cab1,
                arrival=arr_cab1,
                price=cab_price,
                comfort_score=0.6,
                metadata=_geo(o, o),
            ),
            LegOption(
                leg_id=f"leg-t2-{uuid.uuid4().hex[:4]}",
                mode=TransportMode.TRAIN,
                operator="IRCTC",
                origin=f"{o.city or o.name} Station",
                destination=f"{d.city or d.name} Station",
                departure=dep_train,
                arrival=arr_train,
                price=round(train_price, 2),
                comfort_score=0.55,
                metadata=_geo(o, d),
            ),
            LegOption(
                leg_id=f"leg-t3-{uuid.uuid4().hex[:4]}",
                mode=TransportMode.CAB,
                operator="Ola",
                origin=f"{d.city or d.name} Station",
                destination=d.name,
                departure=dep_cab2,
                arrival=arr,
                price=cab_price,
                comfort_score=0.6,
                metadata=_geo(d, d),
            ),
        ]
        total_price = sum(lg.price for lg in legs)
        total_dur = (arr - dep_cab1).total_seconds() / 60.0
        return ItineraryOption(
            itinerary_id=f"itin-trn-{tag}-{uuid.uuid4().hex[:6]}",
            trip_id=trip_id,
            goal_context=goal,
            legs=legs,
            total_price=round(total_price, 2),
            total_duration_minutes=round(total_dur, 1),
            score=0.0,
            explanation="Economy rail option with first/last-mile cabs.",
            metadata={"strategy": "train_chain", "tag": tag},
        )

    def _append_return(
        self,
        opt: ItineraryOption,
        goal: GoalContext,
        o: PlaceInfo,
        d: PlaceInfo,
        origin: dict,
        destination: dict,
        appointment: datetime,
    ) -> ItineraryOption:
        """Clone outbound pattern reversed, departing evening after appointment."""
        return_start = appointment + timedelta(hours=4)
        # Simple return: reverse each leg with +offset prices
        ret_legs: list[LegOption] = []
        t = return_start
        for i, leg in enumerate(reversed(opt.legs)):
            dur = (leg.arrival - leg.departure).total_seconds() / 60.0
            # Reverse the leg, so swap its endpoint coordinates for the map too.
            reversed_geo = {
                k: v
                for k, v in {
                    "from_lat": leg.metadata.get("to_lat"),
                    "from_lng": leg.metadata.get("to_lng"),
                    "to_lat": leg.metadata.get("from_lat"),
                    "to_lng": leg.metadata.get("from_lng"),
                }.items()
                if v is not None
            }
            new_leg = LegOption(
                leg_id=f"ret-{i+1}-{uuid.uuid4().hex[:4]}",
                mode=leg.mode,
                operator=leg.operator,
                origin=leg.destination,
                destination=leg.origin,
                departure=t,
                arrival=t + timedelta(minutes=dur),
                price=round(leg.price * 0.98, 2),
                comfort_score=leg.comfort_score,
                metadata={"direction": "return", **reversed_geo},
            )
            ret_legs.append(new_leg)
            t = new_leg.arrival + timedelta(minutes=25)

        all_legs = list(opt.legs) + ret_legs
        return ItineraryOption(
            itinerary_id=opt.itinerary_id + "-rt",
            trip_id=opt.trip_id,
            goal_context=goal,
            legs=all_legs,
            total_price=round(sum(lg.price for lg in all_legs), 2),
            total_duration_minutes=round(
                (all_legs[-1].arrival - all_legs[0].departure).total_seconds() / 60.0, 1
            ),
            score=0.0,
            explanation=opt.explanation + " Includes return journey.",
            metadata={**opt.metadata, "return": True},
        )

    def _score(self, opt: ItineraryOption, prefs: UserPreferences) -> ItineraryOption:
        # Normalize heuristics
        price_score = max(0.0, 1.0 - opt.total_price / 15000.0)
        time_score = max(0.0, 1.0 - opt.total_duration_minutes / 1200.0)
        comfort = sum(lg.comfort_score for lg in opt.legs) / len(opt.legs)

        modes = {lg.mode.value for lg in opt.legs}
        mode_bonus = 0.0
        for m in prefs.preferred_modes:
            if m in modes:
                mode_bonus += 0.05
        for m in prefs.avoid_modes:
            if m in modes:
                mode_bonus -= 0.15

        w_price = 0.45 if prefs.prefer_cheapest else 0.2
        w_time = 0.45 if prefs.prefer_fastest else 0.25
        w_comfort = 0.35 if prefs.prefer_comfort else 0.15
        total_w = w_price + w_time + w_comfort
        score = (
            w_price * price_score
            + w_time * time_score
            + w_comfort * comfort
        ) / total_w + mode_bonus
        if prefs.max_budget_inr and opt.total_price > prefs.max_budget_inr:
            score -= 0.3

        opt.score = round(max(0.0, min(1.0, score)), 3)
        opt.metadata = {
            **opt.metadata,
            "score_breakdown": {
                "price": round(price_score, 3),
                "time": round(time_score, 3),
                "comfort": round(comfort, 3),
                "mode_bonus": round(mode_bonus, 3),
            },
        }
        return opt

    # ------------------------------------------------------------------
    # Optional LLM narration
    # ------------------------------------------------------------------

    def _llm_recommend(
        self,
        goal: GoalContext,
        prefs: UserPreferences,
        scored: list[ItineraryOption],
    ) -> Optional[str]:
        """One-sentence recommendation for the top itinerary, or None."""
        top = scored[0]
        modes = " → ".join(lg.mode.value for lg in top.legs)
        prefs_summary = ", ".join(
            label
            for flag, label in (
                (prefs.prefer_cheapest, "cheapest"),
                (prefs.prefer_fastest, "fastest"),
                (prefs.prefer_comfort, "comfort"),
            )
            if flag
        ) or "balanced"
        prompt = (
            "You are a mobility assistant. In ONE concise sentence (<= 30 words), "
            "explain why this itinerary suits the traveller. Plain text only.\n\n"
            f"Goal: {goal.goal_statement}\n"
            f"Purpose: {goal.purpose}\n"
            f"Traveller preference: {prefs_summary}\n"
            f"Recommended route: {modes}, "
            f"total ₹{top.total_price:.0f}, "
            f"{top.total_duration_minutes:.0f} min."
        )
        return generate_text(prompt, temperature=0.4)


def buffer_msg(goal: GoalContext) -> str:
    return f"{goal.required_buffer_minutes} min"
