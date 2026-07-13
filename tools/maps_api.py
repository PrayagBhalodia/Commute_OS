"""Maps / distance / geocode tools for DMOS.

Uses Google Maps REST APIs when GOOGLE_MAPS_API_KEY is set.
Falls back to offline haversine + India place catalog for the prototype.
"""

from __future__ import annotations

import math
import os
from typing import Any, Optional

from tools.places_india import (
    INDIA_PLACES,
    get_place_by_id,
    list_places,
    nearest_airport,
    resolve_place_name,
)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def google_maps_enabled() -> bool:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    return bool(key) and httpx is not None


def _google_key() -> str:
    return os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()


def geocode(query: str) -> Optional[dict[str, Any]]:
    """Resolve a free-text place to lat/lng.

    Prefers offline India catalog; optionally enriches via Google Geocoding.
    """
    local = resolve_place_name(query)
    if local and not google_maps_enabled():
        return {
            **local,
            "source": "catalog",
        }

    if google_maps_enabled() and query.strip():
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {"address": query, "region": "in", "key": _google_key()}
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(url, params=params)
                data = resp.json()
            if data.get("status") == "OK" and data.get("results"):
                r0 = data["results"][0]
                loc = r0["geometry"]["location"]
                return {
                    "place_id": r0.get("place_id", f"ggl-{hash(query) & 0xFFFF:x}"),
                    "name": r0.get("formatted_address", query).split(",")[0],
                    "address": r0.get("formatted_address", query),
                    "city": None,
                    "state": None,
                    "lat": float(loc["lat"]),
                    "lng": float(loc["lng"]),
                    "place_type": "custom",
                    "source": "google_geocode",
                    "metadata": {"google_types": r0.get("types", [])},
                }
        except Exception:
            # Fall through to local catalog / heuristic
            pass

    if local:
        return {**local, "source": "catalog"}

    # Last resort: treat as custom label at India centroid-ish
    return None


def reverse_geocode(lat: float, lng: float) -> dict[str, Any]:
    """Nearest catalog place or Google reverse geocode."""
    if google_maps_enabled():
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {"latlng": f"{lat},{lng}", "key": _google_key()}
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(url, params=params)
                data = resp.json()
            if data.get("status") == "OK" and data.get("results"):
                r0 = data["results"][0]
                return {
                    "place_id": r0.get("place_id", f"ggl-rev-{lat:.3f}-{lng:.3f}"),
                    "name": r0.get("formatted_address", "Current location").split(",")[0],
                    "address": r0.get("formatted_address", f"{lat:.5f},{lng:.5f}"),
                    "city": None,
                    "state": None,
                    "lat": lat,
                    "lng": lng,
                    "place_type": "custom",
                    "source": "google_reverse",
                }
        except Exception:
            pass

    best = min(
        INDIA_PLACES,
        key=lambda p: haversine_km(lat, lng, p["lat"], p["lng"]),
    )
    dist = haversine_km(lat, lng, best["lat"], best["lng"])
    if dist < 25:
        return {**best, "source": "nearest_catalog", "distance_to_match_km": round(dist, 2)}
    return {
        "place_id": f"custom-{lat:.4f}-{lng:.4f}",
        "name": f"Pin ({lat:.4f}, {lng:.4f})",
        "address": f"Custom location {lat:.5f}, {lng:.5f}, India",
        "city": None,
        "state": None,
        "lat": lat,
        "lng": lng,
        "place_type": "custom",
        "source": "coordinates",
    }


def distance_matrix(
    origin: dict[str, Any],
    destination: dict[str, Any],
    mode: str = "driving",
) -> dict[str, Any]:
    """Distance & duration between two places.

    Google Distance Matrix when configured; else haversine + speed model.
    """
    o_lat, o_lng = float(origin["lat"]), float(origin["lng"])
    d_lat, d_lng = float(destination["lat"]), float(destination["lng"])
    straight = haversine_km(o_lat, o_lng, d_lat, d_lng)

    if google_maps_enabled():
        try:
            url = "https://maps.googleapis.com/maps/api/distancematrix/json"
            params = {
                "origins": f"{o_lat},{o_lng}",
                "destinations": f"{d_lat},{d_lng}",
                "mode": mode if mode in ("driving", "walking", "transit") else "driving",
                "region": "in",
                "key": _google_key(),
            }
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(url, params=params)
                data = resp.json()
            el = data["rows"][0]["elements"][0]
            if el.get("status") == "OK":
                return {
                    "distance_km": el["distance"]["value"] / 1000.0,
                    "duration_minutes": el["duration"]["value"] / 60.0,
                    "source": "google_distance_matrix",
                    "mode": mode,
                }
        except Exception:
            pass

    # Offline road-factor + speed by mode
    road_factor = 1.35 if mode == "driving" else 1.15
    dist = straight * road_factor
    speeds = {
        "driving": 35.0,  # urban India average
        "walking": 5.0,
        "transit": 28.0,
        "flight": 700.0,
    }
    speed = speeds.get(mode, 35.0)
    if dist > 250 and mode == "driving":
        speed = 55.0  # highway-ish
    duration = (dist / speed) * 60.0
    return {
        "distance_km": round(dist, 2),
        "duration_minutes": round(duration, 1),
        "source": "haversine_model",
        "mode": mode,
        "straight_line_km": round(straight, 2),
    }


def resolve_origin_destination(
    origin_text: Optional[str] = None,
    destination_text: Optional[str] = None,
    origin_lat: Optional[float] = None,
    origin_lng: Optional[float] = None,
    destination_lat: Optional[float] = None,
    destination_lng: Optional[float] = None,
) -> tuple[dict[str, Any], dict[str, Any], float]:
    """Resolve origin & destination from text and/or coordinates."""
    if origin_lat is not None and origin_lng is not None:
        origin = reverse_geocode(origin_lat, origin_lng)
        if origin_text:
            origin["name"] = origin_text
            origin["label"] = origin_text
    elif origin_text:
        origin = geocode(origin_text)
        if origin is None:
            origin = {
                "place_id": "unknown-origin",
                "name": origin_text,
                "address": origin_text,
                "lat": 23.0225,
                "lng": 72.5714,
                "place_type": "custom",
                "source": "fallback_ahmedabad",
            }
    else:
        origin = get_place_by_id("in-amd") or INDIA_PLACES[0]

    if destination_lat is not None and destination_lng is not None:
        destination = reverse_geocode(destination_lat, destination_lng)
        if destination_text:
            destination["name"] = destination_text
    elif destination_text:
        destination = geocode(destination_text)
        if destination is None:
            destination = {
                "place_id": "unknown-dest",
                "name": destination_text,
                "address": destination_text,
                "lat": 19.0760,
                "lng": 72.8777,
                "place_type": "custom",
                "source": "fallback_mumbai",
            }
    else:
        destination = get_place_by_id("in-jio") or INDIA_PLACES[0]

    dm = distance_matrix(origin, destination, mode="driving")
    return origin, destination, float(dm["distance_km"])


def directions_summary(
    origin: dict[str, Any],
    destination: dict[str, Any],
) -> dict[str, Any]:
    """High-level multimodal routing hint for journey composition."""
    dm = distance_matrix(origin, destination, mode="driving")
    dist = dm["distance_km"]
    o_airport = nearest_airport(origin)
    d_airport = nearest_airport(destination)
    same_metro = (
        (origin.get("city") or "").lower() == (destination.get("city") or "").lower()
        and origin.get("city")
    )
    return {
        "distance_km": dist,
        "duration_minutes_driving": dm["duration_minutes"],
        "same_city": bool(same_metro) or dist < 40,
        "suggest_flight": dist > 250,
        "suggest_train": 80 < dist <= 800,
        "suggest_cab_only": dist <= 80,
        "origin_airport": o_airport,
        "destination_airport": d_airport,
        "source": dm.get("source"),
    }


__all__ = [
    "haversine_km",
    "google_maps_enabled",
    "geocode",
    "reverse_geocode",
    "distance_matrix",
    "resolve_origin_destination",
    "directions_summary",
    "list_places",
    "nearest_airport",
]
