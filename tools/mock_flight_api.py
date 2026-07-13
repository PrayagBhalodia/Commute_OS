"""Mock flight operator adapter (IndiGo / Air India / Akasa style).

Local simulation only — no network calls.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Optional


_BASE_FARES: dict[tuple[str, str], float] = {
    ("Ahmedabad Airport", "Mumbai Airport"): 4200.0,
    ("Mumbai Airport", "Ahmedabad Airport"): 4100.0,
    ("Ahmedabad", "Mumbai"): 4200.0,
    ("Mumbai", "Ahmedabad"): 4100.0,
    ("Delhi", "Bengaluru"): 5500.0,
    ("Bengaluru", "Delhi"): 5400.0,
    ("Hyderabad", "Pune"): 3800.0,
    ("Pune", "Hyderabad"): 3700.0,
}

# Distance-based fare model (used when a route isn't in the table above).
_FLIGHT_BASE_FARE = 1800.0    # fixed component (taxes, airport fees)
_FLIGHT_PER_KM = 5.5          # sector distance component
_FLIGHT_MIN_FARE = 2500.0
_FLIGHT_FLAT_FALLBACK = 4500.0  # legacy fallback when distance is unknown


def _flight_base_fare(
    origin: str, destination: str, distance_km: Optional[float]
) -> float:
    """Base flight fare: curated route → distance model → flat fallback."""
    table = _BASE_FARES.get((origin, destination))
    if table is not None:
        return table
    if distance_km is not None and distance_km > 0:
        return max(_FLIGHT_MIN_FARE, _FLIGHT_BASE_FARE + distance_km * _FLIGHT_PER_KM)
    return _FLIGHT_FLAT_FALLBACK


def _stable_ref(prefix: str, seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6].upper()
    return f"{prefix}-{digest}"


def _simulate_latency(latency_seconds: float) -> None:
    if latency_seconds > 0:
        time.sleep(latency_seconds)


def _should_fail(force_failure: bool, failure_rate: float, seed: str) -> bool:
    if force_failure:
        return True
    if failure_rate <= 0:
        return False
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16)
    return (h % 10000) / 10000.0 < failure_rate


def get_flight_quotes(
    origin: str,
    destination: str,
    operator: str = "IndiGo",
    distance_km: Optional[float] = None,
    failure_rate: float = 0.05,
    latency_seconds: float = 0.05,
    force_failure: bool = False,
) -> list[dict[str, Any]]:
    """Return mock flight quotes for origin → destination.

    When ``distance_km`` is supplied, the sector fare scales with distance.
    """
    _simulate_latency(latency_seconds)
    seed = f"quote-flt-{origin}-{destination}-{operator}"
    if _should_fail(force_failure, failure_rate, seed):
        return []

    base = _flight_base_fare(origin, destination, distance_km)
    operators = [operator] if operator else ["IndiGo", "Air India", "Akasa Air"]
    quotes: list[dict[str, Any]] = []
    for idx, op in enumerate(operators):
        op_mult = 1.0 + (idx * 0.08)
        quotes.append(
            {
                "success": True,
                "mode": "flight",
                "operator": op,
                "origin": origin,
                "destination": destination,
                "amount": round(base * op_mult, 2),
                "currency": "INR",
                "service_id": f"FLT-{op[:3].upper()}-6E",
                "duration_minutes": 95,
                "message": f"Flight quote from {op}",
            }
        )
    return quotes


def book_flight(
    origin: str,
    destination: str,
    operator: str = "IndiGo",
    amount: Optional[float] = None,
    service_id: Optional[str] = None,
    trip_id: str = "",
    leg_id: str = "",
    failure_rate: float = 0.05,
    latency_seconds: float = 0.05,
    force_failure: bool = False,
) -> dict[str, Any]:
    """Book a mock flight. Returns a normalized result dictionary."""
    _simulate_latency(latency_seconds)
    seed = f"book-flt-{trip_id}-{leg_id}-{origin}-{destination}-{operator}"
    if _should_fail(force_failure, failure_rate, seed):
        return {
            "success": False,
            "booking_ref": None,
            "amount": amount or 0.0,
            "operator": operator,
            "mode": "flight",
            "service_id": service_id,
            "status": "failed",
            "message": f"Flight booking failed for {operator}: simulated inventory error",
        }

    charged = amount
    if charged is None:
        quotes = get_flight_quotes(
            origin,
            destination,
            operator=operator,
            failure_rate=0.0,
            latency_seconds=0.0,
            force_failure=False,
        )
        charged = quotes[0]["amount"] if quotes else 4500.0

    booking_ref = _stable_ref("FLT", seed or str(uuid.uuid4()))
    return {
        "success": True,
        "booking_ref": booking_ref,
        "amount": float(charged),
        "operator": operator,
        "mode": "flight",
        "service_id": service_id or f"FLT-{operator[:3].upper()}-6E",
        "status": "confirmed",
        "message": f"Flight booked with {operator}",
        "origin": origin,
        "destination": destination,
    }


def cancel_flight(
    booking_ref: str,
    operator: str = "IndiGo",
    failure_rate: float = 0.0,
    latency_seconds: float = 0.05,
    force_failure: bool = False,
) -> dict[str, Any]:
    """Cancel a mock flight booking."""
    _simulate_latency(latency_seconds)
    seed = f"cancel-flt-{booking_ref}-{operator}"
    if _should_fail(force_failure, failure_rate, seed):
        return {
            "success": False,
            "booking_ref": booking_ref,
            "operator": operator,
            "mode": "flight",
            "status": "failed",
            "message": f"Flight cancellation failed for {booking_ref}",
        }
    return {
        "success": True,
        "booking_ref": booking_ref,
        "operator": operator,
        "mode": "flight",
        "status": "cancelled",
        "message": f"Flight booking {booking_ref} cancelled",
    }
