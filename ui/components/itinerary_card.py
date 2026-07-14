"""Render helpers for itinerary option cards."""

from __future__ import annotations

from typing import Any


def itinerary_summary(itin: dict[str, Any]) -> str:
    legs = itin.get("legs") or []
    modes = " → ".join(
        f"{lg.get('mode', '?')}({lg.get('operator', '?')})" for lg in legs
    )
    return (
        f"**{itin.get('itinerary_id')}**\n\n"
        f"₹{itin.get('total_price', 0):.0f} · "
        f"{itin.get('total_duration_minutes', 0):.0f} min\n\n"
        f"{modes}\n\n"
        f"_{itin.get('explanation', '')}_"
    )


def leg_lines(itin: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for i, lg in enumerate(itin.get("legs") or [], 1):
        lines.append(
            f"{i}. [{lg.get('mode')}] {lg.get('operator')}: "
            f"{lg.get('origin')} → {lg.get('destination')} · ₹{lg.get('price', 0):.0f}"
        )
    return lines
