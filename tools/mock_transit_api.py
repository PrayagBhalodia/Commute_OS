"""Mock transit operator adapter (train / bus / metro / auto).

Local simulation only — no network calls.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Optional

from api.schemas import TransportMode


_BASE_FARES: dict[str, dict[tuple[str, str], float]] = {
    "train": {
        ("Ahmedabad", "Mumbai"): 850.0,
        ("Mumbai", "Ahmedabad"): 850.0,
        ("Delhi", "Bengaluru"): 1200.0,
    },
    "bus": {
        ("Ahmedabad", "Pune"): 650.0,
        ("Pune", "Ahmedabad"): 650.0,
        ("Mumbai", "Pune"): 400.0,
    },
    "metro": {
        ("Ahmedabad", "Ahmedabad Airport"): 40.0,
        ("Mumbai Airport", "Navi Mumbai"): 55.0,
        ("Mumbai", "Navi Mumbai"): 45.0,
    },
    "auto": {
        ("Ahmedabad", "Ahmedabad Airport"): 280.0,
        ("Navi Mumbai", "Jio Institute"): 150.0,
        ("Jio Institute", "Navi Mumbai"): 150.0,
    },
}

_MODE_PREFIX = {
    "train": "TRN",
    "bus": "BUS",
    "metro": "MTR",
    "auto": "ATO",
}

# Per-mode distance fare model: (base_fare, per_km, min_fare) in INR.
# Used when a corridor isn't in the curated table above.
_MODE_RATES: dict[str, tuple[float, float, float]] = {
    "train": (120.0, 1.0, 150.0),   # AC chair / sleeper blend
    "bus": (80.0, 1.6, 100.0),      # intercity coach
    "metro": (10.0, 0.6, 15.0),     # short urban hops
    "auto": (30.0, 12.0, 40.0),     # last-mile auto-rickshaw
}


def _transit_base_fare(
    mode_key: str, origin: str, destination: str, distance_km: Optional[float]
) -> float:
    """Fare: curated corridor → per-mode distance model → flat fallback."""
    table = _BASE_FARES.get(mode_key, {}).get((origin, destination))
    if table is not None:
        return table
    if distance_km is not None and distance_km > 0:
        base_c, per_km, min_c = _MODE_RATES.get(mode_key, (120.0, 1.0, 100.0))
        return max(min_c, base_c + distance_km * per_km)
    return 40.0 if mode_key == "metro" else 200.0


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


def _normalize_mode(mode: str | TransportMode) -> str:
    if isinstance(mode, TransportMode):
        return mode.value
    return str(mode).lower()


def get_transit_quotes(
    origin: str,
    destination: str,
    mode: str | TransportMode = "train",
    operator: str = "IRCTC",
    distance_km: Optional[float] = None,
    failure_rate: float = 0.05,
    latency_seconds: float = 0.05,
    force_failure: bool = False,
) -> list[dict[str, Any]]:
    """Return mock transit quotes for the given mode.

    When ``distance_km`` is supplied, the fare scales per-mode with distance.
    """
    mode_key = _normalize_mode(mode)
    _simulate_latency(latency_seconds)
    seed = f"quote-trn-{mode_key}-{origin}-{destination}-{operator}"
    if _should_fail(force_failure, failure_rate, seed):
        return []

    base = _transit_base_fare(mode_key, origin, destination, distance_km)
    return [
        {
            "success": True,
            "mode": mode_key,
            "operator": operator,
            "origin": origin,
            "destination": destination,
            "amount": round(base, 2),
            "currency": "INR",
            "service_id": f"{_MODE_PREFIX.get(mode_key, 'TRN')}-SVC-1",
            "message": f"{mode_key.title()} quote from {operator}",
        }
    ]


def book_transit(
    origin: str,
    destination: str,
    mode: str | TransportMode = "train",
    operator: str = "IRCTC",
    amount: Optional[float] = None,
    service_id: Optional[str] = None,
    trip_id: str = "",
    leg_id: str = "",
    failure_rate: float = 0.05,
    latency_seconds: float = 0.05,
    force_failure: bool = False,
) -> dict[str, Any]:
    """Book a mock transit leg. Returns a normalized result dictionary."""
    mode_key = _normalize_mode(mode)
    _simulate_latency(latency_seconds)
    seed = f"book-trn-{mode_key}-{trip_id}-{leg_id}-{origin}-{destination}-{operator}"
    if _should_fail(force_failure, failure_rate, seed):
        return {
            "success": False,
            "booking_ref": None,
            "amount": amount or 0.0,
            "operator": operator,
            "mode": mode_key,
            "service_id": service_id,
            "status": "failed",
            "message": f"{mode_key.title()} booking failed for {operator}",
        }

    charged = amount
    if charged is None:
        quotes = get_transit_quotes(
            origin,
            destination,
            mode=mode_key,
            operator=operator,
            failure_rate=0.0,
            latency_seconds=0.0,
            force_failure=False,
        )
        charged = quotes[0]["amount"] if quotes else 200.0

    prefix = _MODE_PREFIX.get(mode_key, "TRN")
    booking_ref = _stable_ref(prefix, seed or str(uuid.uuid4()))
    return {
        "success": True,
        "booking_ref": booking_ref,
        "amount": float(charged),
        "operator": operator,
        "mode": mode_key,
        "service_id": service_id or f"{prefix}-SVC-1",
        "status": "confirmed",
        "message": f"{mode_key.title()} booked with {operator}",
        "origin": origin,
        "destination": destination,
    }


def cancel_transit(
    booking_ref: str,
    mode: str | TransportMode = "train",
    operator: str = "IRCTC",
    failure_rate: float = 0.0,
    latency_seconds: float = 0.05,
    force_failure: bool = False,
) -> dict[str, Any]:
    """Cancel a mock transit booking."""
    mode_key = _normalize_mode(mode)
    _simulate_latency(latency_seconds)
    seed = f"cancel-trn-{mode_key}-{booking_ref}-{operator}"
    if _should_fail(force_failure, failure_rate, seed):
        return {
            "success": False,
            "booking_ref": booking_ref,
            "operator": operator,
            "mode": mode_key,
            "status": "failed",
            "message": f"{mode_key.title()} cancellation failed for {booking_ref}",
        }
    return {
        "success": True,
        "booking_ref": booking_ref,
        "operator": operator,
        "mode": mode_key,
        "status": "cancelled",
        "message": f"{mode_key.title()} booking {booking_ref} cancelled",
    }
