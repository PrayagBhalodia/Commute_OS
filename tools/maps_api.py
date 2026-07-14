"""Maps / distance / geocode tools for DMOS.

Geocoding provider order (each optional, always degrades gracefully):
  1. Offline India place catalog  — fast, curated, works with zero config.
  2. OpenStreetMap Nominatim       — free, no API key, for unknown free text.
  3. Google Maps                   — only when GOOGLE_MAPS_API_KEY is set.
Distances always use the offline haversine + speed model unless Google's
Distance Matrix is configured.
"""

from __future__ import annotations

import math
import os
import threading
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


# ---------------------------------------------------------------------------
# OpenStreetMap / Nominatim (free geocoder, no API key required)
# ---------------------------------------------------------------------------

_NOMINATIM_BASE = os.environ.get(
    "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
).rstrip("/")
# Nominatim's usage policy requires a descriptive, contactable User-Agent.
_NOMINATIM_UA = os.environ.get(
    "NOMINATIM_USER_AGENT", "DMOS-CommuteSuperapp/1.0 (contact: set NOMINATIM_USER_AGENT)"
)
# Simple process-wide cache to respect the ~1 req/sec rate limit.
_geo_cache: dict[str, Optional[dict[str, Any]]] = {}
_geo_lock = threading.Lock()

# OSM place types that represent an area/locality rather than a specific
# business or landmark inside it (used to disambiguate a bare area name
# like "Koramangala" from a same-named POI like "Nexus Koramangala").
_LOCALITY_OSM_TYPES = {
    "suburb", "neighbourhood", "quarter", "city_district", "town",
    "village", "hamlet", "city", "borough", "state_district", "county",
    "administrative",
}
_POI_OSM_CLASSES = {"shop", "amenity", "tourism", "leisure", "office", "craft"}


def _score_nominatim_candidate(candidate: dict[str, Any], query_lower: str) -> tuple[int, int]:
    name = (candidate.get("name") or "").strip().lower()
    osm_class = candidate.get("class") or ""
    osm_type = candidate.get("type") or ""
    exact = 1 if name == query_lower else 0
    bias = 0
    if osm_class == "place" and osm_type in _LOCALITY_OSM_TYPES:
        bias += 1
    if osm_class in _POI_OSM_CLASSES and not exact:
        bias -= 1
    return (exact, bias)


def _pick_best_nominatim_result(
    candidates: list[dict[str, Any]], query: str
) -> dict[str, Any]:
    """Pick the best geocode match out of Nominatim's ranked candidates.

    Nominatim's own top hit for a bare area name (e.g. "Koramangala") is
    sometimes a well-known POI within that area (e.g. a mall named "Nexus
    Koramangala") rather than the area itself. Since the query was just the
    area name, prefer an exact name match, then prefer locality/administrative
    results over shops/malls/amenities. Ties fall back to Nominatim's own
    ranking (candidate order).
    """
    query_lower = query.strip().lower()
    best = candidates[0]
    best_score = _score_nominatim_candidate(best, query_lower)
    for candidate in candidates[1:]:
        score = _score_nominatim_candidate(candidate, query_lower)
        if score > best_score:
            best, best_score = candidate, score
    return best


def nominatim_enabled() -> bool:
    """True unless explicitly disabled and httpx is importable."""
    flag = os.environ.get("DMOS_USE_NOMINATIM", "1").strip().lower()
    return flag not in ("0", "false", "no", "off") and httpx is not None


def _nominatim_search(query: str) -> Optional[dict[str, Any]]:
    """Free-text geocode via Nominatim; cached, None on any failure."""
    key = f"s:{query.strip().lower()}"
    with _geo_lock:
        if key in _geo_cache:
            return _geo_cache[key]
    result: Optional[dict[str, Any]] = None
    try:
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": 5,
            "addressdetails": 1,
            "countrycodes": "in",
        }
        with httpx.Client(timeout=8.0, headers={"User-Agent": _NOMINATIM_UA}) as client:
            resp = client.get(f"{_NOMINATIM_BASE}/search", params=params)
            data = resp.json()
        if isinstance(data, list) and data:
            r0 = _pick_best_nominatim_result(data, query)
            addr = r0.get("address", {}) or {}
            result = {
                "place_id": f"osm-{r0.get('osm_type', 'n')[0]}{r0.get('osm_id', '')}",
                "name": (r0.get("name") or r0.get("display_name", query).split(",")[0]).strip(),
                "address": r0.get("display_name", query),
                "city": addr.get("city") or addr.get("town") or addr.get("village")
                or addr.get("state_district"),
                "state": addr.get("state"),
                "lat": float(r0["lat"]),
                "lng": float(r0["lon"]),
                "place_type": "custom",
                "metadata": {"osm_class": r0.get("class"), "osm_type_detail": r0.get("type")},
            }
    except Exception:  # noqa: BLE001
        result = None
    with _geo_lock:
        _geo_cache[key] = result
    return result


def _nominatim_reverse(lat: float, lng: float) -> Optional[dict[str, Any]]:
    """Reverse geocode via Nominatim; cached, None on any failure."""
    key = f"r:{lat:.4f},{lng:.4f}"
    with _geo_lock:
        if key in _geo_cache:
            return _geo_cache[key]
    result: Optional[dict[str, Any]] = None
    try:
        params = {"lat": lat, "lon": lng, "format": "jsonv2", "addressdetails": 1}
        with httpx.Client(timeout=8.0, headers={"User-Agent": _NOMINATIM_UA}) as client:
            resp = client.get(f"{_NOMINATIM_BASE}/reverse", params=params)
            data = resp.json()
        if isinstance(data, dict) and data.get("lat"):
            addr = data.get("address", {}) or {}
            result = {
                "place_id": f"osm-{data.get('osm_type', 'n')[0]}{data.get('osm_id', '')}",
                "name": (data.get("name") or data.get("display_name", "").split(",")[0]).strip()
                or f"Pin ({lat:.4f}, {lng:.4f})",
                "address": data.get("display_name", f"{lat:.5f},{lng:.5f}"),
                "city": addr.get("city") or addr.get("town") or addr.get("village"),
                "state": addr.get("state"),
                "lat": lat,
                "lng": lng,
                "place_type": "custom",
            }
    except Exception:  # noqa: BLE001
        result = None
    with _geo_lock:
        _geo_cache[key] = result
    return result


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

    Order: curated India catalog → free Nominatim → Google (if configured).
    """
    # 1. Curated catalog is authoritative for known India places (offline, and
    #    carries airport/city metadata the journey builder relies on).
    local = resolve_place_name(query)
    if local:
        return {**local, "source": "catalog"}

    # 2. Free OpenStreetMap Nominatim for anything not in the catalog.
    if nominatim_enabled() and query.strip():
        nom = _nominatim_search(query)
        if nom:
            return {**nom, "source": "nominatim"}

    # 3. Optional Google Geocoding when a key is configured.
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
            # Fall through to None below.
            pass

    # Last resort: unresolved.
    return None


def reverse_geocode(lat: float, lng: float) -> dict[str, Any]:
    """Resolve coordinates to a place.

    Order: nearest curated catalog place (≤25 km) → free Nominatim → Google
    (if configured) → raw coordinate pin.
    """
    best = min(
        INDIA_PLACES,
        key=lambda p: haversine_km(lat, lng, p["lat"], p["lng"]),
    )
    dist = haversine_km(lat, lng, best["lat"], best["lng"])
    if dist < 25:
        return {**best, "source": "nearest_catalog", "distance_to_match_km": round(dist, 2)}

    if nominatim_enabled():
        nom = _nominatim_reverse(lat, lng)
        if nom:
            return {**nom, "source": "nominatim"}

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
    "nominatim_enabled",
    "geocode",
    "reverse_geocode",
    "distance_matrix",
    "resolve_origin_destination",
    "directions_summary",
    "list_places",
    "nearest_airport",
]
