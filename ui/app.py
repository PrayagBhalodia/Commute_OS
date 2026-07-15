"""DMOS Streamlit UI — bare-minimum working OS frontend.

Talk to the OS in goals, pick origin/destination on an India map,
inspect agent chain-of-thought, confirm booking, give feedback, simulate disruption.

Run (with API already up on :8000):
  streamlit run ui/app.py

Or let this app call the orchestrator in-process (no separate API needed):
  set DMOS_UI_MODE=local
  streamlit run ui/app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

import streamlit as st

# Repo root on path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.components.chat_input import EXAMPLE_GOALS, format_goal_prompt
from ui.components.disruption_trigger_button import DISRUPTION_REASONS, SEVERITIES
from ui.components.itinerary_card import itinerary_summary, leg_lines

API_BASE = os.environ.get("DMOS_API_BASE", "http://127.0.0.1:8000")
UI_MODE = os.environ.get("DMOS_UI_MODE", "local")  # local | api


# ---------------------------------------------------------------------------
# Backend adapters
# ---------------------------------------------------------------------------


@st.cache_resource
def get_orchestrator():
    from orchestration.orchestrator import DMOSOrchestrator

    return DMOSOrchestrator()


def api_post(path: str, payload: dict) -> dict:
    import httpx

    with httpx.Client(timeout=60.0) as client:
        r = client.post(f"{API_BASE}{path}", json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"API {r.status_code}: {r.text}")
        return r.json()


def api_get(path: str) -> Any:
    import httpx

    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{API_BASE}{path}")
        if r.status_code >= 400:
            raise RuntimeError(f"API {r.status_code}: {r.text}")
        return r.json()


def do_plan(payload: dict) -> dict:
    if UI_MODE == "api":
        return api_post("/os/plan", payload)
    from api.schemas import PlanRequest

    orch = get_orchestrator()
    return orch.plan(PlanRequest.model_validate(payload)).model_dump(mode="json")


def do_confirm(payload: dict) -> dict:
    if UI_MODE == "api":
        return api_post("/os/confirm", payload)
    from api.schemas import ConfirmPlanRequest

    orch = get_orchestrator()
    return orch.confirm_and_book(
        ConfirmPlanRequest.model_validate(payload)
    ).model_dump(mode="json")


def do_disrupt(payload: dict) -> dict:
    if UI_MODE == "api":
        return api_post("/os/disrupt", payload)
    from api.schemas import DisruptionRequest

    orch = get_orchestrator()
    return orch.handle_disruption(
        DisruptionRequest.model_validate(payload)
    ).model_dump(mode="json")


def do_feedback(payload: dict) -> dict:
    if UI_MODE == "api":
        return api_post("/os/feedback", payload)
    from api.schemas import FeedbackRequest

    orch = get_orchestrator()
    return orch.submit_feedback(
        FeedbackRequest.model_validate(payload)
    ).model_dump(mode="json")


def do_topup(user_id: str, amount: float) -> dict:
    if UI_MODE == "api":
        return api_post(
            f"/wallet/{user_id}/topup",
            {"amount": amount, "trip_id": "ui", "description": "UI top-up"},
        )
    orch = get_orchestrator()
    return orch.wallet.topup(
        user_id, amount, trip_id="ui", description="UI top-up"
    ).model_dump(mode="json")


def do_balance(user_id: str) -> dict:
    if UI_MODE == "api":
        return api_get(f"/wallet/{user_id}/balance")
    orch = get_orchestrator()
    return orch.wallet.get_balance(user_id).model_dump(mode="json")


def do_places() -> list[dict]:
    if UI_MODE == "api":
        try:
            return api_get("/places")
        except Exception:
            pass
    from tools.places_india import list_places

    return list_places()


def do_prefs(user_id: str) -> dict:
    if UI_MODE == "api":
        try:
            return api_get(f"/os/preferences/{user_id}")
        except Exception:
            return {}
    return get_orchestrator().get_preferences(user_id).model_dump(mode="json")


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def init_state() -> None:
    defaults = {
        "user_id": "user-demo",
        "messages": [],
        "plan": None,
        "booking": None,
        "cot": [],
        "selected_itin": None,
        "origin_name": "Ahmedabad",
        "dest_name": "Jio Institute",
        "origin_lat": 23.0225,
        "origin_lng": 72.5714,
        "dest_lat": 18.9800,
        "dest_lng": 73.0300,
        "disruption_result": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def render_cot(steps: list[dict]) -> None:
    if not steps:
        st.info("No chain-of-thought steps yet.")
        return
    phase_emoji = {
        "thought": "💭",
        "action": "⚙️",
        "observation": "👁",
        "decision": "✅",
        "wait_user": "⏸",
    }
    for s in steps:
        emoji = phase_emoji.get(s.get("phase", ""), "•")
        agent = s.get("agent") or "os"
        with st.expander(
            f"{emoji} Step {s.get('step_id')}: [{s.get('phase')}] {s.get('title')} · {agent}",
            expanded=s.get("phase") in ("decision", "wait_user"),
        ):
            st.write(s.get("detail", ""))
            if s.get("data"):
                st.json(s["data"])


@st.cache_data(show_spinner=False)
def geocode_point(name: str) -> Optional[tuple[float, float]]:
    """Resolve a place name to (lat, lng) via the catalog + Nominatim. Cached."""
    if not name:
        return None
    try:
        from tools.maps_api import geocode

        g = geocode(name)
        if g:
            return float(g["lat"]), float(g["lng"])
    except Exception:
        pass
    return None


@st.cache_data(show_spinner=False)
def reverse_geocode_name(lat: float, lng: float) -> Optional[str]:
    """Real place name for coordinates, so a "current location" pin shows
    where it actually is. Cached; None on any failure."""
    try:
        from tools.maps_api import reverse_geocode

        place = reverse_geocode(lat, lng)
        name = (place.get("name") or "").strip()
        if name and not name.startswith("Pin ("):
            return name
    except Exception:
        pass
    return None


@st.cache_data(show_spinner=False)
def osrm_route(start: tuple[float, float], end: tuple[float, float]) -> Optional[list[list[float]]]:
    """Real driving-road geometry [[lng,lat], …] via the free OSRM API. Cached.

    Returns None on any failure so the caller can fall back to a synthetic line.
    """
    import httpx

    try:
        url = (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{start[1]},{start[0]};{end[1]},{end[0]}"
        )
        r = httpx.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            timeout=8.0,
            headers={"User-Agent": "DMOS-CommuteSuperapp/1.0"},
        )
        data = r.json()
        if data.get("code") == "Ok" and data.get("routes"):
            return data["routes"][0]["geometry"]["coordinates"]
    except Exception:
        pass
    return None


def wavy_line(
    start: tuple[float, float],
    end: tuple[float, float],
    waves: int = 6,
    amplitude_frac: float = 0.05,
    n: int = 64,
) -> list[list[float]]:
    """A gently wavy [[lng,lat], …] line between two points (road illustration).

    Amplitude is proportional to the leg length so short and long hops both look
    natural. Used when real road geometry is unavailable.
    """
    import math

    (lat1, lng1), (lat2, lng2) = start, end
    dlat, dlng = lat2 - lat1, lng2 - lng1
    dist = math.hypot(dlat, dlng)
    if dist == 0:
        return [[lng1, lat1], [lng2, lat2]]
    # Unit vector perpendicular to the leg direction, in (lng, lat) space.
    perp_lng, perp_lat = -dlat / dist, dlng / dist
    amp = amplitude_frac * dist
    pts: list[list[float]] = []
    for i in range(n + 1):
        t = i / n
        base_lat = lat1 + dlat * t
        base_lng = lng1 + dlng * t
        # Fade the wave out at both ends so it meets the stops cleanly.
        envelope = math.sin(t * math.pi)
        off = math.sin(t * math.pi * waves) * amp * envelope
        pts.append([base_lng + perp_lng * off, base_lat + perp_lat * off])
    return pts


# Modes drawn as roads (follow real road geometry / wavy); others fly straight.
_ROAD_MODES = {"cab", "auto", "bus", "metro", "train"}
_ROAD_COLOR = [0, 120, 255]      # blue road
_AIR_COLOR = [255, 140, 0]       # orange flight hop


def build_route(itin: dict) -> dict:
    """Build map geometry for an itinerary.

    Returns {"waypoints": [{lat,lng,name}], "segments": [{path,color,mode}]}
    where road legs follow real road geometry (OSRM) or a wavy fallback, and
    flight legs are drawn as a straight hop.
    """
    waypoints: list[dict] = []
    segments: list[dict] = []
    prev_name: Optional[str] = None

    def add_wp(name: Optional[str], latlng: Optional[tuple[float, float]]) -> None:
        nonlocal prev_name
        if name and name != prev_name and latlng:
            waypoints.append({"lat": latlng[0], "lng": latlng[1], "name": name})
        if name:
            prev_name = name

    for lg in itin.get("legs") or []:
        o_name, d_name = lg.get("origin"), lg.get("destination")
        o = geocode_point(o_name) if o_name else None
        d = geocode_point(d_name) if d_name else None
        add_wp(o_name, o)
        add_wp(d_name, d)
        if not (o and d):
            continue
        mode = str(lg.get("mode", "")).lower()
        if mode in _ROAD_MODES:
            path = osrm_route(o, d) or wavy_line(o, d)
            color = _ROAD_COLOR
        else:  # flight (and any unknown mode) → straight hop
            path = [[o[1], o[0]], [d[1], d[0]]]
            color = _AIR_COLOR
        segments.append({"path": path, "color": color, "mode": mode})

    return {"waypoints": waypoints, "segments": segments}


def build_od_route() -> dict:
    """Pre-plan geometry: a single road leg from origin → destination."""
    o = (st.session_state.origin_lat, st.session_state.origin_lng)
    d = (st.session_state.dest_lat, st.session_state.dest_lng)
    path = osrm_route(o, d) or wavy_line(o, d)
    return {
        "waypoints": [
            {"lat": o[0], "lng": o[1], "name": f"Origin · {st.session_state.origin_name}"},
            {"lat": d[0], "lng": d[1], "name": f"Destination · {st.session_state.dest_name}"},
        ],
        "segments": [{"path": path, "color": _ROAD_COLOR, "mode": "cab"}],
    }


def render_map(route: dict) -> None:
    """Draw the route (road-following segments + relative-size stops)."""
    import pandas as pd
    import pydeck as pdk

    waypoints = route.get("waypoints") or []
    segments = route.get("segments") or []
    if not waypoints:
        st.info("Enter an origin and destination to see the route.")
        return

    layers = []

    # Route segments: road legs follow real roads; flights are straight hops.
    if segments:
        seg_df = pd.DataFrame(
            [{"path": s["path"], "color": s["color"]} for s in segments]
        )
        layers.append(
            pdk.Layer(
                "PathLayer",
                data=seg_df,
                get_path="path",
                get_color="color",
                width_min_pixels=4,
                get_width=5,
                cap_rounded=True,
                joint_rounded=True,
            )
        )

    # Waypoint markers with RELATIVE sizes: origin/destination big, stops small.
    n = len(waypoints)
    wp_rows = []
    for i, p in enumerate(waypoints):
        if i == 0:
            color, radius = [0, 170, 70], 12000        # origin — green, large
        elif i == n - 1:
            color, radius = [220, 45, 45], 12000        # destination — red, large
        else:
            color, radius = [255, 160, 0], 6000         # stop — amber, small
        wp_rows.append(
            {"lat": p["lat"], "lon": p["lng"], "name": p["name"], "color": color, "radius": radius}
        )
    wp_df = pd.DataFrame(wp_rows)
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=wp_df,
            get_position="[lon, lat]",
            get_fill_color="color",
            get_radius="radius",
            radius_min_pixels=5,
            radius_max_pixels=16,
            stroked=True,
            get_line_color="[255, 255, 255]",
            line_width_min_pixels=1,
            pickable=True,
        )
    )
    layers.append(
        pdk.Layer(
            "TextLayer",
            data=wp_df,
            get_position="[lon, lat]",
            get_text="name",
            get_size=13,
            get_color="[20, 20, 20]",
            get_alignment_baseline="'bottom'",
        )
    )

    # Center on the route with a span-based zoom.
    lats = [p["lat"] for p in waypoints]
    lngs = [p["lng"] for p in waypoints]
    span = max(max(lats) - min(lats), max(lngs) - min(lngs))
    zoom = 9.0 if span < 0.4 else 7.5 if span < 1.5 else 6.0 if span < 4 else 4.6
    view = pdk.ViewState(
        latitude=sum(lats) / len(lats),
        longitude=sum(lngs) / len(lngs),
        zoom=zoom,
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            initial_view_state=view,
            map_provider="carto",
            map_style="light",
            tooltip={"text": "{name}"},
        )
    )


def main() -> None:
    st.set_page_config(
        page_title="DMOS — Daily Mobility OS",
        page_icon="🧭",
        layout="wide",
    )
    init_state()

    st.title("🧭 DMOS — Daily Mobility Operating System")
    st.caption(
        "Goal-oriented AI OS for commute. You state life goals; agents figure out transport. "
        "**Prototype** — bookings & payments are simulated."
    )

    # Sidebar
    with st.sidebar:
        st.header("Session")
        st.session_state.user_id = st.text_input("User ID", st.session_state.user_id)
        st.write(f"UI mode: `{UI_MODE}`")
        if UI_MODE == "api":
            st.write(f"API: `{API_BASE}`")

        st.subheader("Wallet")
        try:
            bal = do_balance(st.session_state.user_id)
            st.metric("Balance (INR)", f"₹{bal.get('balance', 0):.2f}")
        except Exception as exc:
            st.warning(f"Wallet unavailable: {exc}")

        top_amt = st.number_input("Top-up amount", min_value=100.0, value=10000.0, step=500.0)
        if st.button("Top up wallet"):
            try:
                s = do_topup(st.session_state.user_id, float(top_amt))
                st.success(f"Balance ₹{s.get('balance', 0):.2f}")
            except Exception as exc:
                st.error(str(exc))

        st.subheader("Learned preferences")
        prefs = do_prefs(st.session_state.user_id)
        if prefs:
            st.json(
                {
                    "preferred_modes": prefs.get("preferred_modes"),
                    "avoid_modes": prefs.get("avoid_modes"),
                    "prefer_cheapest": prefs.get("prefer_cheapest"),
                    "prefer_fastest": prefs.get("prefer_fastest"),
                    "prefer_comfort": prefs.get("prefer_comfort"),
                    "interaction_count": prefs.get("interaction_count"),
                }
            )

        st.divider()
        st.markdown(
            "This prototype simulates booking and payments. "
            "It does not perform real transportation bookings or real financial transactions."
        )

    col_left, col_right = st.columns([1.1, 1])

    with col_left:
        st.subheader("1. Your goal")
        st.write(format_goal_prompt(st.session_state.user_id))
        example = st.selectbox("Quick examples", ["(type your own)"] + EXAMPLE_GOALS)
        default_goal = example if example != "(type your own)" else (
            st.session_state.messages[-1]["content"]
            if st.session_state.messages
            else EXAMPLE_GOALS[0]
        )
        goal_text = st.text_area("Goal statement", value=default_goal, height=100)

        st.subheader("2. Origin & destination")
        st.caption("Type an address, or switch on coordinates to use a current location.")
        c1, c2 = st.columns(2)
        with c1:
            origin_addr = st.text_input(
                "Origin address", value="Ahmedabad", placeholder="e.g. Rajkot, Gujarat"
            )
            use_origin_coords = st.checkbox("Use coordinates (current location)", key="oc")
            origin_lat_in = origin_lng_in = None
            if use_origin_coords:
                origin_lat_in = st.number_input("Origin latitude", value=23.0225, format="%.6f")
                origin_lng_in = st.number_input("Origin longitude", value=72.5714, format="%.6f")
        with c2:
            dest_addr = st.text_input(
                "Destination address", value="Jio Institute", placeholder="e.g. Mumbai Airport"
            )
            use_dest_coords = st.checkbox("Use coordinates (current location)", key="dc")
            dest_lat_in = dest_lng_in = None
            if use_dest_coords:
                dest_lat_in = st.number_input("Destination latitude", value=18.9800, format="%.6f")
                dest_lng_in = st.number_input("Destination longitude", value=73.0300, format="%.6f")

        # Resolve display coordinates for the map (address → geocode, or coords).
        if use_origin_coords and origin_lat_in is not None:
            st.session_state.origin_lat = float(origin_lat_in)
            st.session_state.origin_lng = float(origin_lng_in)
            st.session_state.origin_name = (
                origin_addr.strip()
                or reverse_geocode_name(float(origin_lat_in), float(origin_lng_in))
                or "Current location"
            )
        elif origin_addr.strip():
            st.session_state.origin_name = origin_addr.strip()
            g = geocode_point(origin_addr.strip())
            if g:
                st.session_state.origin_lat, st.session_state.origin_lng = g
        if use_dest_coords and dest_lat_in is not None:
            st.session_state.dest_lat = float(dest_lat_in)
            st.session_state.dest_lng = float(dest_lng_in)
            st.session_state.dest_name = dest_addr.strip() or "Dropped pin"
        elif dest_addr.strip():
            st.session_state.dest_name = dest_addr.strip()
            g = geocode_point(dest_addr.strip())
            if g:
                st.session_state.dest_lat, st.session_state.dest_lng = g

        st.subheader("Route map")
        # If a plan exists, trace the selected itinerary's legs; otherwise show
        # the origin → destination road.
        _plan = st.session_state.plan
        if _plan and _plan.get("itineraries"):
            _sel = st.session_state.selected_itin or _plan["itineraries"][0]["itinerary_id"]
            _chosen = next(
                (i for i in _plan["itineraries"] if i["itinerary_id"] == _sel),
                _plan["itineraries"][0],
            )
            route = build_route(_chosen)
            if route["waypoints"]:
                st.caption("Route: " + " → ".join(p["name"] for p in route["waypoints"]))
        else:
            route = build_od_route()
        render_map(route)

        if st.button("🚀 Plan my journey", type="primary", use_container_width=True):
            payload = {
                "user_id": st.session_state.user_id,
                "goal_text": goal_text,
                "origin": origin_addr.strip() or st.session_state.origin_name,
                "destination": dest_addr.strip() or st.session_state.dest_name,
                "origin_lat": float(origin_lat_in) if use_origin_coords else None,
                "origin_lng": float(origin_lng_in) if use_origin_coords else None,
                "destination_lat": float(dest_lat_in) if use_dest_coords else None,
                "destination_lng": float(dest_lng_in) if use_dest_coords else None,
                "max_options": 3,
            }
            # Drop null coords for cleaner local validate
            payload = {k: v for k, v in payload.items() if v is not None}
            try:
                with st.spinner("Agents thinking (Intent → Maps → Journey)…"):
                    plan = do_plan(payload)
                st.session_state.plan = plan
                st.session_state.cot = plan.get("chain_of_thought") or []
                st.session_state.messages.append({"role": "user", "content": goal_text})
                st.session_state.messages.append(
                    {"role": "assistant", "content": plan.get("message", "Planned.")}
                )
                st.session_state.booking = None
                st.session_state.disruption_result = None
                if plan.get("itineraries"):
                    st.session_state.selected_itin = plan["itineraries"][0]["itinerary_id"]
                st.success(plan.get("message", "Plan ready"))
            except Exception as exc:
                st.error(f"Plan failed: {exc}")

    with col_right:
        st.subheader("3. Chain of thought")
        render_cot(st.session_state.cot)

        plan = st.session_state.plan
        if plan and plan.get("itineraries"):
            st.subheader("4. Choose itinerary")
            itins = plan["itineraries"]
            labels = {
                i["itinerary_id"]: f"{i['itinerary_id']} · ₹{i['total_price']:.0f} · score {i['score']:.2f}"
                for i in itins
            }
            pick = st.radio(
                "Options ranked for you",
                options=list(labels.keys()),
                format_func=lambda k: labels[k],
                index=0,
            )
            st.session_state.selected_itin = pick
            chosen = next(i for i in itins if i["itinerary_id"] == pick)
            st.markdown(itinerary_summary(chosen))
            for line in leg_lines(chosen):
                st.write(line)

            consent = st.checkbox("I confirm booking these legs (human-in-the-loop)", value=False)
            if st.button("✅ Confirm & book", disabled=not consent, use_container_width=True):
                try:
                    with st.spinner("Agent 3 booking · Agent 4 wallet…"):
                        conf = do_confirm(
                            {
                                "trip_id": plan["trip_id"],
                                "user_id": st.session_state.user_id,
                                "itinerary_id": pick,
                                "user_confirmed": True,
                            }
                        )
                    st.session_state.booking = conf
                    st.session_state.cot = (st.session_state.cot or []) + (
                        conf.get("chain_of_thought") or []
                    )
                    if conf.get("status") == "confirmed":
                        st.success(conf.get("message", "Booked"))
                    else:
                        st.warning(conf.get("message", conf.get("status")))
                except Exception as exc:
                    st.error(str(exc))

        booking = st.session_state.booking
        if booking and booking.get("booking"):
            b = booking["booking"]
            st.subheader("5. Booking confirmation")
            st.write(f"Trip **{b.get('trip_id')}** · status **{b.get('status')}**")
            st.write(f"Total charged: ₹{b.get('total_charged', 0):.2f}")
            for lc in b.get("leg_confirmations") or []:
                st.write(
                    f"- {lc.get('leg_id')}: `{lc.get('booking_ref')}` "
                    f"[{lc.get('status')}] ₹{lc.get('price_charged', 0):.2f}"
                )

            st.subheader("6. Simulate disruption (Agent 5)")
            reason = st.selectbox(
                "Reason",
                DISRUPTION_REASONS,
                format_func=lambda x: x[1],
            )
            severity = st.selectbox("Severity", SEVERITIES, index=1)
            if st.button("⚠ Trigger disruption & reroute", use_container_width=True):
                try:
                    with st.spinner("Agent 5 cancelling / recomposing / rebooking…"):
                        dr = do_disrupt(
                            {
                                "trip_id": b["trip_id"],
                                "user_id": st.session_state.user_id,
                                "reason": reason[0],
                                "severity": severity,
                                "auto_rebook": True,
                            }
                        )
                    st.session_state.disruption_result = dr
                    st.session_state.cot = (st.session_state.cot or []) + (
                        dr.get("chain_of_thought") or []
                    )
                    st.warning(dr.get("message", "Disruption handled"))
                except Exception as exc:
                    st.error(str(exc))

            if st.session_state.disruption_result:
                st.json(
                    {
                        k: st.session_state.disruption_result.get(k)
                        for k in (
                            "status",
                            "cancelled_legs",
                            "refund_total",
                            "message",
                        )
                    }
                )

        st.subheader("7. Teach the OS (feedback)")
        rating = st.slider("Rating", 1, 5, 4)
        comment = st.text_input("Comment (e.g. prefer cheaper / avoid flights)")
        preferred = st.selectbox(
            "Preferred mode signal",
            ["", "cab", "flight", "train", "metro", "bus"],
        )
        if st.button("Submit feedback"):
            try:
                prefs = do_feedback(
                    {
                        "user_id": st.session_state.user_id,
                        "trip_id": (plan or {}).get("trip_id"),
                        "rating": rating,
                        "comment": comment or None,
                        "preferred_mode": preferred or None,
                        "liked": rating >= 4,
                    }
                )
                st.success(
                    f"Preferences updated · interactions={prefs.get('interaction_count')}"
                )
            except Exception as exc:
                st.error(str(exc))


if __name__ == "__main__":
    main()
