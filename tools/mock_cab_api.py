"""Mock cab operator adapter (Ola / Uber style).

Local simulation only — no network calls. Designed to be replaced by real
partner APIs later while keeping the same adapter surface.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Optional


# Known corridors keep curated fares so demo routes stay stable (INR).
_BASE_FARES: dict[tuple[str, str], float] = {
    ("Ahmedabad", "Ahmedabad Airport"): 450.0,
    ("Ahmedabad Airport", "Ahmedabad"): 450.0,
    ("Mumbai Airport", "Jio Institute"): 850.0,
    ("Jio Institute", "Mumbai Airport"): 850.0,
    ("Mumbai Airport", "Navi Mumbai"): 700.0,
    ("Navi Mumbai", "Mumbai Airport"): 700.0,
    ("Delhi", "Bengaluru"): 0.0,  # not a cab corridor
}

# Distance-based fare model (used when a corridor isn't in the table above).
_CAB_PICKUP_FARE = 50.0       # flat pickup / base
_CAB_PER_KM_CITY = 15.0       # ≤ 100 km (city / short outstation)
_CAB_PER_KM_LONG = 12.0       # > 100 km (outstation slab)
_CAB_MIN_FARE = 80.0
_CAB_FLAT_FALLBACK = 350.0    # legacy fallback when distance is unknown


def _cab_base_fare(
    origin: str, destination: str, distance_km: Optional[float]
) -> float:
    """Base cab fare before luggage: curated corridor → distance model → flat."""
    table = _BASE_FARES.get((origin, destination))
    if table is not None:
        return table
    if distance_km is not None and distance_km > 0:
        per_km = _CAB_PER_KM_CITY if distance_km <= 100 else _CAB_PER_KM_LONG
        return max(_CAB_MIN_FARE, _CAB_PICKUP_FARE + distance_km * per_km)
    return _CAB_FLAT_FALLBACK


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
    # Deterministic pseudo-random from seed for reproducible demos.
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16)
    return (h % 10000) / 10000.0 < failure_rate


def get_cab_quotes(
    origin: str,
    destination: str,
    operator: str = "Ola",
    luggage_count: int = 0,
    distance_km: Optional[float] = None,
    failure_rate: float = 0.05,
    latency_seconds: float = 0.05,
    force_failure: bool = False,
) -> list[dict[str, Any]]:
    """Return mock cab quotes for origin → destination.

    When ``distance_km`` is supplied, the fare scales with distance instead of
    using a flat fallback, so long corridors are priced realistically.
    """
    _simulate_latency(latency_seconds)
    seed = f"quote-cab-{origin}-{destination}-{operator}"
    if _should_fail(force_failure, failure_rate, seed):
        return []

    base = _cab_base_fare(origin, destination, distance_km)
    luggage_surcharge = max(0, luggage_count) * 50.0
    amount = base + luggage_surcharge
    operators = [operator] if operator else ["Ola", "Uber"]
    quotes: list[dict[str, Any]] = []
    for op in operators:
        op_mult = 1.05 if op == "Uber" else 1.0
        quotes.append(
            {
                "success": True,
                "mode": "cab",
                "operator": op,
                "origin": origin,
                "destination": destination,
                "amount": round(amount * op_mult, 2),
                "currency": "INR",
                "service_id": f"CAB-SVC-{op[:3].upper()}",
                "eta_minutes": 12,
                "message": f"Quote from {op}",
            }
        )
    return quotes


def book_cab(
    origin: str,
    destination: str,
    operator: str = "Ola",
    amount: Optional[float] = None,
    service_id: Optional[str] = None,
    trip_id: str = "",
    leg_id: str = "",
    failure_rate: float = 0.05,
    latency_seconds: float = 0.05,
    force_failure: bool = False,
) -> dict[str, Any]:
    """Book a mock cab. Returns a normalized result dictionary."""
    _simulate_latency(latency_seconds)
    seed = f"book-cab-{trip_id}-{leg_id}-{origin}-{destination}-{operator}"
    if _should_fail(force_failure, failure_rate, seed):
        return {
            "success": False,
            "booking_ref": None,
            "amount": amount or 0.0,
            "operator": operator,
            "mode": "cab",
            "service_id": service_id,
            "status": "failed",
            "message": f"Cab booking failed for {operator}: simulated operator error",
        }

    charged = amount
    if charged is None:
        quotes = get_cab_quotes(
            origin,
            destination,
            operator=operator,
            failure_rate=0.0,
            latency_seconds=0.0,
            force_failure=False,
        )
        charged = quotes[0]["amount"] if quotes else 350.0

    booking_ref = _stable_ref(
        "CAB",
        seed or str(uuid.uuid4()),
    )
    return {
        "success": True,
        "booking_ref": booking_ref,
        "amount": float(charged),
        "operator": operator,
        "mode": "cab",
        "service_id": service_id or f"CAB-SVC-{operator[:3].upper()}",
        "status": "confirmed",
        "message": f"Cab booked with {operator}",
        "origin": origin,
        "destination": destination,
    }


def cancel_cab(
    booking_ref: str,
    operator: str = "Ola",
    failure_rate: float = 0.0,
    latency_seconds: float = 0.05,
    force_failure: bool = False,
) -> dict[str, Any]:
    """Cancel a mock cab booking."""
    _simulate_latency(latency_seconds)
    seed = f"cancel-cab-{booking_ref}-{operator}"
    if _should_fail(force_failure, failure_rate, seed):
        return {
            "success": False,
            "booking_ref": booking_ref,
            "operator": operator,
            "mode": "cab",
            "status": "failed",
            "message": f"Cab cancellation failed for {booking_ref}",
        }
    return {
        "success": True,
        "booking_ref": booking_ref,
        "operator": operator,
        "mode": "cab",
        "status": "cancelled",
        "message": f"Cab booking {booking_ref} cancelled",
    }
