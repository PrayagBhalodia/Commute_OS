"""Maps / distance / geocode tools for DMOS.

Geocoding provider order (each optional, always degrades gracefully):
  1. Offline India place catalog  — fast, curated, works with zero config.
  2. LocationIQ                    — free API key (LOCATIONIQ_API_KEY in .env).
  3. OpenStreetMap Nominatim       — free, no API key, for unknown free text.
  4. Google Maps                   — only when GOOGLE_MAPS_API_KEY is set.
Distances always use the offline haversine + speed model unless Google's
Distance Matrix is configured.
"""

from __future__ import annotations

import math
import os
import re
import threading
from typing import Any, Optional

from tools.places_india import (
    INDIA_PLACES,
    list_places,
    nearest_airport,
    resolve_place_name,
)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore


# ---------------------------------------------------------------------------
# LocationIQ (free API key, Nominatim-compatible responses) and
# OpenStreetMap / Nominatim (free geocoder, no API key required)
# ---------------------------------------------------------------------------

_LOCATIONIQ_BASE = os.environ.get(
    "LOCATIONIQ_BASE_URL", "https://us1.locationiq.com/v1"
).rstrip("/")


def _locationiq_key() -> str:
    return os.environ.get("LOCATIONIQ_API_KEY", "").strip()


def locationiq_enabled() -> bool:
    return bool(_locationiq_key()) and httpx is not None


_NOMINATIM_BASE = os.environ.get(
    "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
).rstrip("/")
# Nominatim's usage policy requires a descriptive, contactable User-Agent.
_NOMINATIM_UA = os.environ.get(
    "NOMINATIM_USER_AGENT", "DMOS-CommuteSuperapp/1.0 (contact: set NOMINATIM_USER_AGENT)"
)
# Return place names in English (romanised) rather than the local script, so an
# international destination like "Japan" reads as "Japan" instead of "日本".
_NOMINATIM_LANG = os.environ.get("NOMINATIM_LANGUAGE", "en").strip() or "en"
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

# OSM types that mark a result as a whole administrative region rather than a
# routable point. Drives the chat agent's "where in <place>?" follow-ups for
# any country/state/city worldwide, replacing the old hardcoded India lists.
_STATE_OSM_TYPES = {"state", "province", "region"}
_CITY_OSM_TYPES = {"city", "town", "municipality"}


def _osm_place_rank(
    candidate: dict[str, Any], address: dict[str, Any], fallback_name: str = ""
) -> str:
    """Coarse specificity of an OSM result: country / state / city / specific."""
    addresstype = (candidate.get("addresstype") or "").lower()
    osm_type = (candidate.get("type") or "").lower()
    for value in (addresstype, osm_type):
        if value == "country":
            return "country"
        if value in _STATE_OSM_TYPES:
            return "state"
        if value in _CITY_OSM_TYPES:
            return "city"
    if (candidate.get("class") or "") == "boundary" and osm_type == "administrative":
        # Admin boundary without an addresstype (e.g. LocationIQ's v1 JSON):
        # infer the level from which address component carries the same name.
        name = (candidate.get("name") or fallback_name or "").strip().lower()
        if name and (address.get("country") or "").lower() == name:
            return "country"
        if name and (address.get("state") or address.get("region") or "").lower() == name:
            return "state"
        if name and (
            address.get("city") or address.get("town") or address.get("municipality") or ""
        ).lower() == name:
            return "city"
    return "specific"


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


def _geo_providers() -> list[dict[str, Any]]:
    """Ordered OSM-compatible geocoders to try: LocationIQ first, then Nominatim.

    LocationIQ (keyed, higher free limits) is tried first when a key is set; the
    public Nominatim instance is a keyless fallback, so a LocationIQ outage or
    quota error still resolves places. LocationIQ only supports ``format=json``
    while Nominatim additionally supports the richer ``jsonv2``.
    """
    providers: list[dict[str, Any]] = []
    if locationiq_enabled():
        providers.append(
            {
                "source": "locationiq",
                "base": _LOCATIONIQ_BASE,
                "extra": {"key": _locationiq_key()},
                "headers": {},
                "format": "json",
            }
        )
    if nominatim_enabled():
        providers.append(
            {
                "source": "nominatim",
                "base": _NOMINATIM_BASE,
                "extra": {},
                "headers": {"User-Agent": _NOMINATIM_UA},
                "format": "jsonv2",
            }
        )
    return providers


def _nominatim_search(query: str) -> Optional[dict[str, Any]]:
    """Free-text geocode via LocationIQ/Nominatim; cached, None on failure."""
    key = f"s:{query.strip().lower()}"
    with _geo_lock:
        if key in _geo_cache:
            return _geo_cache[key]
    result: Optional[dict[str, Any]] = None
    for provider in _geo_providers():
        try:
            params: dict[str, Any] = {
                "q": query,
                "format": provider["format"],
                "limit": 5,
                "addressdetails": 1,
                **provider["extra"],
            }
            # Geocode worldwide by default so international destinations (e.g.
            # "Japan") resolve to the real country rather than a same-named
            # place inside India. Set NOMINATIM_COUNTRYCODES (comma-separated
            # ISO codes, e.g. "in") to restrict the search back to countries.
            _cc = os.environ.get("NOMINATIM_COUNTRYCODES", "").strip()
            if _cc:
                params["countrycodes"] = _cc
            params["accept-language"] = _NOMINATIM_LANG
            with httpx.Client(timeout=8.0, headers=provider["headers"]) as client:
                resp = client.get(f"{provider['base']}/search", params=params)
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
                    "place_rank": _osm_place_rank(r0, addr, query),
                    "source": provider["source"],
                    "metadata": {"osm_class": r0.get("class"), "osm_type_detail": r0.get("type")},
                }
                break
        except Exception:  # noqa: BLE001 — try the next provider
            continue
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
    for provider in _geo_providers():
        try:
            params = {
                "lat": lat,
                "lon": lng,
                "format": provider["format"],
                "addressdetails": 1,
                "accept-language": _NOMINATIM_LANG,
                **provider["extra"],
            }
            with httpx.Client(timeout=8.0, headers=provider["headers"]) as client:
                resp = client.get(f"{provider['base']}/reverse", params=params)
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
                    "source": provider["source"],
                }
                break
        except Exception:  # noqa: BLE001 — try the next provider
            continue
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

    Order: curated India catalog → Google (if configured) → free
    LocationIQ/Nominatim.
    """
    # 1. Curated catalog is authoritative for known India places (offline, and
    #    carries airport/city metadata the journey builder relies on).
    local = resolve_place_name(query)
    if local:
        return {**local, "source": "catalog"}

    # 2. Prefer Google Geocoding when a key is configured.
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
            # Fall through to the keyless provider below.
            pass

    # 3. Free LocationIQ / OpenStreetMap Nominatim for anything not in the
    #    catalog (the search itself already tries LocationIQ first, then
    #    Nominatim, and tags the winning provider in "source").
    if (locationiq_enabled() or nominatim_enabled()) and query.strip():
        nom = _nominatim_search(query)
        if nom:
            return nom

    # Last resort: unresolved.
    return None


def classify_place(text: str) -> str:
    """How narrowly free-text pins a place, for any region worldwide.

    Returns "country", "state", "city", "specific" (locality/landmark/
    address/POI), or "unknown" (could not resolve). Uses the same provider
    chain as ``geocode`` (catalog → LocationIQ/Nominatim → Google), so the
    chat agent's "where in <place>?" drill-down works for any country,
    state, or city instead of a hardcoded list.
    """
    query = re.sub(r"^the\s+", "", (text or "").strip(), flags=re.IGNORECASE)
    if not query:
        return "unknown"

    # Prefer the live geocoder's admin-level rank: it distinguishes
    # country/state/city accurately worldwide. The offline catalog uses fuzzy
    # substring matching (e.g. "Gujarat" → a landmark inside it), which is good
    # for routing but wrong for "is this a whole region?", so only fall back to
    # it when no online provider is available.
    if locationiq_enabled() or nominatim_enabled():
        nom = _nominatim_search(query)
        if nom and nom.get("place_rank"):
            return str(nom["place_rank"])

    place = geocode(query)
    if not place:
        return "unknown"
    rank = place.get("place_rank")
    if rank:
        return str(rank)
    google_types = (place.get("metadata") or {}).get("google_types") or []
    if "country" in google_types:
        return "country"
    if "administrative_area_level_1" in google_types:
        return "state"
    if "locality" in google_types:
        return "city"
    place_type = place.get("place_type")
    if place_type == "city":
        return "city"
    if place_type in ("airport", "landmark", "locality", "custom"):
        return "specific"
    return "unknown"


def reverse_geocode(lat: float, lng: float) -> dict[str, Any]:
    """Resolve coordinates to a place.

    Order: free LocationIQ/Nominatim (precise street/locality names) →
    Google (if configured) → nearest curated catalog place (≤25 km, offline
    fallback) → raw coordinate pin.
    """
    # Live reverse geocoding first: it names the actual locality/landmark at
    # the pin, while the offline catalog can only snap to the nearest city
    # centroid (e.g. "Ahmedabad" instead of "Navrangpura").
    if locationiq_enabled() or nominatim_enabled():
        nom = _nominatim_reverse(lat, lng)
        if nom:
            return nom

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

    # Offline fallback: nearest curated catalog place within 25 km.
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
        "address": f"Custom location {lat:.5f}, {lng:.5f}",
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
        # A meaningful user-supplied name wins, but a generic placeholder must
        # not hide the reverse-geocoded place name in itineraries and maps.
        if origin_text and origin_text.strip().lower() not in {
            "current location", "my current location", "my location", "here",
        }:
            origin["name"] = origin_text
            origin["label"] = origin_text
    elif origin_text:
        origin = geocode(origin_text)
        if origin is None:
            # No silent fallback to a hardcoded city: surface the problem so
            # the user is asked for a resolvable starting point instead.
            raise ValueError(
                f"Could not resolve the origin '{origin_text}' to a location. "
                "Please provide a more specific place name."
            )
    else:
        raise ValueError("An origin (place name or coordinates) is required.")

    if destination_lat is not None and destination_lng is not None:
        destination = reverse_geocode(destination_lat, destination_lng)
        if destination_text:
            destination["name"] = destination_text
    elif destination_text:
        destination = geocode(destination_text)
        if destination is None:
            raise ValueError(
                f"Could not resolve the destination '{destination_text}' to a "
                "location. Please provide a more specific place name."
            )
    else:
        raise ValueError("A destination (place name or coordinates) is required.")

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
    "locationiq_enabled",
    "geocode",
    "classify_place",
    "reverse_geocode",
    "distance_matrix",
    "resolve_origin_destination",
    "directions_summary",
    "list_places",
    "nearest_airport",
]
