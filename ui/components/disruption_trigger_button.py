"""Disruption simulation labels for the UI."""

from __future__ import annotations

DISRUPTION_REASONS = [
    ("traffic_delay", "Traffic delay on last-mile cab"),
    ("flight_delay", "Flight delayed / missed connection"),
    ("operator_cancel", "Operator cancelled service"),
    ("weather", "Weather disruption"),
]

SEVERITIES = ["low", "medium", "high"]
