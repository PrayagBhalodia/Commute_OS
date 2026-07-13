"""Chat-style goal input helpers for the Streamlit UI."""

from __future__ import annotations

EXAMPLE_GOALS = [
    "I have an interview tomorrow at Jio Institute in Navi Mumbai. One suitcase, arrive one hour early, return same evening.",
    "Need to reach IIT Bombay from Ahmedabad tomorrow for a meeting, prefer fastest option.",
    "Weekend trip from Delhi to Jaipur, budget friendly, no flights.",
    "Drop me at Mumbai Airport from Navi Mumbai in 2 hours with one bag.",
]


def format_goal_prompt(user_id: str) -> str:
    return (
        f"Hi {user_id} — tell me your **goal**, not the route. "
        "Example: *I have an interview tomorrow at Jio Institute.*"
    )
