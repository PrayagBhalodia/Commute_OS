"""India place catalog for DMOS prototype geocoding and map pins.

Works offline. When Google Maps is configured, maps_api can refine results.
"""

from __future__ import annotations

import math
from typing import Any, Optional


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# Curated India mobility hubs / cities / landmarks for the prototype map.
INDIA_PLACES: list[dict[str, Any]] = [
    # Cities
    {"place_id": "in-amd", "name": "Ahmedabad", "address": "Ahmedabad, Gujarat, India", "city": "Ahmedabad", "state": "Gujarat", "lat": 23.0225, "lng": 72.5714, "place_type": "city"},
    {"place_id": "in-bom", "name": "Mumbai", "address": "Mumbai, Maharashtra, India", "city": "Mumbai", "state": "Maharashtra", "lat": 19.0760, "lng": 72.8777, "place_type": "city"},
    {"place_id": "in-navi", "name": "Navi Mumbai", "address": "Navi Mumbai, Maharashtra, India", "city": "Navi Mumbai", "state": "Maharashtra", "lat": 19.0330, "lng": 73.0297, "place_type": "city"},
    {"place_id": "in-del", "name": "Delhi", "address": "New Delhi, Delhi, India", "city": "Delhi", "state": "Delhi", "lat": 28.6139, "lng": 77.2090, "place_type": "city"},
    {"place_id": "in-blr", "name": "Bengaluru", "address": "Bengaluru, Karnataka, India", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "lng": 77.5946, "place_type": "city"},
    {"place_id": "in-hyd", "name": "Hyderabad", "address": "Hyderabad, Telangana, India", "city": "Hyderabad", "state": "Telangana", "lat": 17.3850, "lng": 78.4867, "place_type": "city"},
    {"place_id": "in-pnq", "name": "Pune", "address": "Pune, Maharashtra, India", "city": "Pune", "state": "Maharashtra", "lat": 18.5204, "lng": 73.8567, "place_type": "city"},
    {"place_id": "in-maa", "name": "Chennai", "address": "Chennai, Tamil Nadu, India", "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "lng": 80.2707, "place_type": "city"},
    {"place_id": "in-ccu", "name": "Kolkata", "address": "Kolkata, West Bengal, India", "city": "Kolkata", "state": "West Bengal", "lat": 22.5726, "lng": 88.3639, "place_type": "city"},
    {"place_id": "in-jai", "name": "Jaipur", "address": "Jaipur, Rajasthan, India", "city": "Jaipur", "state": "Rajasthan", "lat": 26.9124, "lng": 75.7873, "place_type": "city"},
    {"place_id": "in-cok", "name": "Kochi", "address": "Kochi, Kerala, India", "city": "Kochi", "state": "Kerala", "lat": 9.9312, "lng": 76.2673, "place_type": "city"},
    {"place_id": "in-goi", "name": "Goa", "address": "Panaji, Goa, India", "city": "Goa", "state": "Goa", "lat": 15.4909, "lng": 73.8278, "place_type": "city"},
    # Airports
    {"place_id": "in-amd-apt", "name": "Ahmedabad Airport", "address": "Sardar Vallabhbhai Patel International Airport, Ahmedabad", "city": "Ahmedabad", "state": "Gujarat", "lat": 23.0772, "lng": 72.6347, "place_type": "airport"},
    {"place_id": "in-bom-apt", "name": "Mumbai Airport", "address": "Chhatrapati Shivaji Maharaj International Airport, Mumbai", "city": "Mumbai", "state": "Maharashtra", "lat": 19.0896, "lng": 72.8656, "place_type": "airport"},
    {"place_id": "in-del-apt", "name": "Delhi Airport", "address": "Indira Gandhi International Airport, Delhi", "city": "Delhi", "state": "Delhi", "lat": 28.5562, "lng": 77.1000, "place_type": "airport"},
    {"place_id": "in-blr-apt", "name": "Bengaluru Airport", "address": "Kempegowda International Airport, Bengaluru", "city": "Bengaluru", "state": "Karnataka", "lat": 13.1986, "lng": 77.7066, "place_type": "airport"},
    {"place_id": "in-hyd-apt", "name": "Hyderabad Airport", "address": "Rajiv Gandhi International Airport, Hyderabad", "city": "Hyderabad", "state": "Telangana", "lat": 17.2403, "lng": 78.4294, "place_type": "airport"},
    {"place_id": "in-pnq-apt", "name": "Pune Airport", "address": "Pune International Airport", "city": "Pune", "state": "Maharashtra", "lat": 18.5821, "lng": 73.9197, "place_type": "airport"},
    # Landmarks / campuses
    {"place_id": "in-jio", "name": "Jio Institute", "address": "Jio Institute, Ulwe, Navi Mumbai, Maharashtra", "city": "Navi Mumbai", "state": "Maharashtra", "lat": 18.9800, "lng": 73.0300, "place_type": "landmark"},
    {"place_id": "in-iitb", "name": "IIT Bombay", "address": "IIT Bombay, Powai, Mumbai", "city": "Mumbai", "state": "Maharashtra", "lat": 19.1334, "lng": 72.9133, "place_type": "landmark"},
    {"place_id": "in-isb", "name": "ISB Hyderabad", "address": "Indian School of Business, Gachibowli, Hyderabad", "city": "Hyderabad", "state": "Telangana", "lat": 17.4454, "lng": 78.3498, "place_type": "landmark"},
    {"place_id": "in-iisc", "name": "IISc Bengaluru", "address": "Indian Institute of Science, Bengaluru", "city": "Bengaluru", "state": "Karnataka", "lat": 13.0213, "lng": 77.5671, "place_type": "landmark"},
    {"place_id": "in-gate", "name": "India Gate", "address": "India Gate, New Delhi", "city": "Delhi", "state": "Delhi", "lat": 28.6129, "lng": 77.2295, "place_type": "landmark"},
    {"place_id": "in-gwlr", "name": "Gateway of India", "address": "Gateway of India, Mumbai", "city": "Mumbai", "state": "Maharashtra", "lat": 18.9220, "lng": 72.8347, "place_type": "landmark"},
    {"place_id": "in-stat", "name": "Statue of Unity", "address": "Statue of Unity, Kevadia, Gujarat", "city": "Kevadia", "state": "Gujarat", "lat": 21.8380, "lng": 73.7191, "place_type": "landmark"},
    {"place_id": "in-taj", "name": "Taj Mahal", "address": "Taj Mahal, Agra, Uttar Pradesh", "city": "Agra", "state": "Uttar Pradesh", "lat": 27.1751, "lng": 78.0421, "place_type": "landmark"},
]

# City → nearest major airport place_id
CITY_AIRPORT: dict[str, str] = {
    "ahmedabad": "in-amd-apt",
    "mumbai": "in-bom-apt",
    "navi mumbai": "in-bom-apt",
    "delhi": "in-del-apt",
    "new delhi": "in-del-apt",
    "bengaluru": "in-blr-apt",
    "bangalore": "in-blr-apt",
    "hyderabad": "in-hyd-apt",
    "pune": "in-pnq-apt",
}


def list_places(
    query: Optional[str] = None,
    place_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List or filter India places (case-insensitive substring match)."""
    results = INDIA_PLACES
    if place_type:
        results = [p for p in results if p["place_type"] == place_type]
    if query:
        q = query.strip().lower()
        results = [
            p
            for p in results
            if q in p["name"].lower()
            or q in p["address"].lower()
            or (p.get("city") and q in p["city"].lower())
        ]
    return [dict(p) for p in results]


def get_place_by_id(place_id: str) -> Optional[dict[str, Any]]:
    for p in INDIA_PLACES:
        if p["place_id"] == place_id:
            return dict(p)
    return None


def resolve_place_name(name: str) -> Optional[dict[str, Any]]:
    """Best-effort name resolution against the catalog."""
    if not name or not name.strip():
        return None
    q = name.strip().lower()
    # Exact name
    for p in INDIA_PLACES:
        if p["name"].lower() == q:
            return dict(p)
    # Alias hacks
    aliases = {
        "amd": "ahmedabad",
        "bom": "mumbai",
        "blr": "bengaluru",
        "bangalore": "bengaluru",
        "jio": "jio institute",
        "jio institute navi mumbai": "jio institute",
        "svpi": "ahmedabad airport",
        "csmia": "mumbai airport",
        "igi": "delhi airport",
    }
    q2 = aliases.get(q, q)
    for p in INDIA_PLACES:
        if p["name"].lower() == q2:
            return dict(p)
    # Substring
    matches = list_places(query=q2)
    if matches:
        # Prefer landmarks/airports when mentioned
        for pref in ("landmark", "airport", "city"):
            for m in matches:
                if m["place_type"] == pref:
                    return m
        return matches[0]
    return None


def nearest_airport(city_or_place: str | dict[str, Any]) -> Optional[dict[str, Any]]:
    """Return nearest major airport for a city/place name or place dict."""
    if isinstance(city_or_place, dict):
        city = (city_or_place.get("city") or city_or_place.get("name") or "").lower()
        if city_or_place.get("place_type") == "airport":
            return dict(city_or_place)
    else:
        city = str(city_or_place).lower()
    # Direct map
    for key, apt_id in CITY_AIRPORT.items():
        if key in city:
            return get_place_by_id(apt_id)
    # Fallback: closest airport by haversine from place coords if we have them
    place = city_or_place if isinstance(city_or_place, dict) else resolve_place_name(city)
    if not place:
        return get_place_by_id("in-del-apt")

    airports = [p for p in INDIA_PLACES if p["place_type"] == "airport"]
    best = min(
        airports,
        key=lambda a: _haversine_km(place["lat"], place["lng"], a["lat"], a["lng"]),
    )
    return dict(best)
