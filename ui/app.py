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


def render_map(places: list[dict]) -> None:
    import pandas as pd

    rows = []
    for p in places:
        rows.append(
            {
                "lat": p["lat"],
                "lon": p["lng"],
                "name": p["name"],
                "type": p.get("place_type", ""),
            }
        )
    # Highlight selected O/D
    rows.append(
        {
            "lat": st.session_state.origin_lat,
            "lon": st.session_state.origin_lng,
            "name": f"ORIGIN: {st.session_state.origin_name}",
            "type": "origin",
        }
    )
    rows.append(
        {
            "lat": st.session_state.dest_lat,
            "lon": st.session_state.dest_lng,
            "name": f"DEST: {st.session_state.dest_name}",
            "type": "destination",
        }
    )
    df = pd.DataFrame(rows)
    st.map(df, latitude="lat", longitude="lon", size=40)


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

    places = do_places()
    place_names = [p["name"] for p in places]
    place_by_name = {p["name"]: p for p in places}

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
        c1, c2 = st.columns(2)
        with c1:
            o_choice = st.selectbox(
                "Origin (India catalog)",
                place_names,
                index=place_names.index("Ahmedabad") if "Ahmedabad" in place_names else 0,
            )
            st.session_state.origin_name = o_choice
            st.session_state.origin_lat = place_by_name[o_choice]["lat"]
            st.session_state.origin_lng = place_by_name[o_choice]["lng"]
            origin_manual = st.text_input("Or type origin", value="")
            use_geo = st.checkbox("Use browser-like coords for origin (manual lat/lng)", False)
            if use_geo:
                st.session_state.origin_lat = st.number_input("Origin lat", value=23.0225, format="%.6f")
                st.session_state.origin_lng = st.number_input("Origin lng", value=72.5714, format="%.6f")
                if origin_manual:
                    st.session_state.origin_name = origin_manual
        with c2:
            d_default = "Jio Institute" if "Jio Institute" in place_names else place_names[0]
            d_choice = st.selectbox(
                "Destination (India catalog / map)",
                place_names,
                index=place_names.index(d_default),
            )
            st.session_state.dest_name = d_choice
            st.session_state.dest_lat = place_by_name[d_choice]["lat"]
            st.session_state.dest_lng = place_by_name[d_choice]["lng"]
            dest_manual = st.text_input("Or type destination", value="")
            if dest_manual.strip():
                st.session_state.dest_name = dest_manual.strip()

        st.subheader("India map pins")
        render_map(places)

        if st.button("🚀 Plan my journey", type="primary", use_container_width=True):
            origin = origin_manual.strip() or st.session_state.origin_name
            dest = dest_manual.strip() or st.session_state.dest_name
            payload = {
                "user_id": st.session_state.user_id,
                "goal_text": goal_text,
                "origin": origin,
                "destination": dest,
                "origin_lat": st.session_state.origin_lat if use_geo else None,
                "origin_lng": st.session_state.origin_lng if use_geo else None,
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
