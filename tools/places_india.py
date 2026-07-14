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

# ---------------------------------------------------------------------------
# Neighbourhood / locality gazetteer for major metros.
#
# This is the "dataset" that gives the parser and geocoder precision for
# intra-city trips (e.g. "Koramangala to Indiranagar"): each entry carries an
# accurate lat/lng AND its parent city, so two localities in the same metro
# both resolve inside that metro instead of drifting to a same-named POI or a
# hardcoded fallback city. Coordinates are approximate locality centroids —
# good enough for distance/mode estimation in this prototype. For a larger
# gazetteer, seed this list from GeoNames (IN.txt, feature class "P") or the
# OSM place=suburb/neighbourhood layer.
# ---------------------------------------------------------------------------
INDIA_LOCALITIES: list[dict[str, Any]] = [
    # Bengaluru
    {"place_id": "in-blr-koramangala", "name": "Koramangala", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9352, "lng": 77.6245},
    {"place_id": "in-blr-indiranagar", "name": "Indiranagar", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9719, "lng": 77.6412},
    {"place_id": "in-blr-whitefield", "name": "Whitefield", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9698, "lng": 77.7500},
    {"place_id": "in-blr-hsr", "name": "HSR Layout", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9116, "lng": 77.6389},
    {"place_id": "in-blr-jayanagar", "name": "Jayanagar", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9250, "lng": 77.5938},
    {"place_id": "in-blr-marathahalli", "name": "Marathahalli", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9560, "lng": 77.7010},
    {"place_id": "in-blr-ecity", "name": "Electronic City", "city": "Bengaluru", "state": "Karnataka", "lat": 12.8452, "lng": 77.6602},
    {"place_id": "in-blr-mgroad", "name": "MG Road", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9756, "lng": 77.6068},
    {"place_id": "in-blr-malleshwaram", "name": "Malleshwaram", "city": "Bengaluru", "state": "Karnataka", "lat": 13.0035, "lng": 77.5647},
    {"place_id": "in-blr-hebbal", "name": "Hebbal", "city": "Bengaluru", "state": "Karnataka", "lat": 13.0358, "lng": 77.5970},
    {"place_id": "in-blr-btm", "name": "BTM Layout", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9166, "lng": 77.6101},
    {"place_id": "in-blr-yelahanka", "name": "Yelahanka", "city": "Bengaluru", "state": "Karnataka", "lat": 13.1007, "lng": 77.5963},
    {"place_id": "in-blr-bellandur", "name": "Bellandur", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9260, "lng": 77.6762},
    {"place_id": "in-blr-sarjapur", "name": "Sarjapur Road", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9010, "lng": 77.6870},
    {"place_id": "in-blr-jpnagar", "name": "JP Nagar", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9078, "lng": 77.5851},
    {"place_id": "in-blr-banashankari", "name": "Banashankari", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9255, "lng": 77.5468},
    {"place_id": "in-blr-rajajinagar", "name": "Rajajinagar", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9910, "lng": 77.5520},
    {"place_id": "in-blr-krpuram", "name": "KR Puram", "city": "Bengaluru", "state": "Karnataka", "lat": 13.0075, "lng": 77.6960},
    {"place_id": "in-blr-domlur", "name": "Domlur", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9610, "lng": 77.6380},
    {"place_id": "in-blr-ulsoor", "name": "Ulsoor", "city": "Bengaluru", "state": "Karnataka", "lat": 12.9820, "lng": 77.6210},
    {"place_id": "in-blr-yeshwanthpur", "name": "Yeshwanthpur", "city": "Bengaluru", "state": "Karnataka", "lat": 13.0287, "lng": 77.5540},
    # Mumbai
    {"place_id": "in-bom-andheri", "name": "Andheri", "city": "Mumbai", "state": "Maharashtra", "lat": 19.1197, "lng": 72.8468},
    {"place_id": "in-bom-bandra", "name": "Bandra", "city": "Mumbai", "state": "Maharashtra", "lat": 19.0596, "lng": 72.8295},
    {"place_id": "in-bom-powai", "name": "Powai", "city": "Mumbai", "state": "Maharashtra", "lat": 19.1176, "lng": 72.9060},
    {"place_id": "in-bom-colaba", "name": "Colaba", "city": "Mumbai", "state": "Maharashtra", "lat": 18.9067, "lng": 72.8147},
    {"place_id": "in-bom-dadar", "name": "Dadar", "city": "Mumbai", "state": "Maharashtra", "lat": 19.0178, "lng": 72.8478},
    {"place_id": "in-bom-juhu", "name": "Juhu", "city": "Mumbai", "state": "Maharashtra", "lat": 19.1075, "lng": 72.8263},
    {"place_id": "in-bom-worli", "name": "Worli", "city": "Mumbai", "state": "Maharashtra", "lat": 19.0176, "lng": 72.8175},
    {"place_id": "in-bom-goregaon", "name": "Goregaon", "city": "Mumbai", "state": "Maharashtra", "lat": 19.1663, "lng": 72.8526},
    {"place_id": "in-bom-bkc", "name": "Bandra Kurla Complex", "city": "Mumbai", "state": "Maharashtra", "lat": 19.0662, "lng": 72.8690},
    {"place_id": "in-navi-vashi", "name": "Vashi", "city": "Navi Mumbai", "state": "Maharashtra", "lat": 19.0770, "lng": 72.9986},
    # Delhi NCR
    {"place_id": "in-del-cp", "name": "Connaught Place", "city": "Delhi", "state": "Delhi", "lat": 28.6315, "lng": 77.2167},
    {"place_id": "in-del-saket", "name": "Saket", "city": "Delhi", "state": "Delhi", "lat": 28.5245, "lng": 77.2066},
    {"place_id": "in-del-dwarka", "name": "Dwarka", "city": "Delhi", "state": "Delhi", "lat": 28.5921, "lng": 77.0460},
    {"place_id": "in-del-karolbagh", "name": "Karol Bagh", "city": "Delhi", "state": "Delhi", "lat": 28.6512, "lng": 77.1907},
    {"place_id": "in-del-hauzkhas", "name": "Hauz Khas", "city": "Delhi", "state": "Delhi", "lat": 28.5494, "lng": 77.2001},
    {"place_id": "in-del-nehruplace", "name": "Nehru Place", "city": "Delhi", "state": "Delhi", "lat": 28.5495, "lng": 77.2519},
    {"place_id": "in-ncr-gurgaon", "name": "Gurgaon", "city": "Gurugram", "state": "Haryana", "lat": 28.4595, "lng": 77.0266},
    {"place_id": "in-ncr-noida", "name": "Noida", "city": "Noida", "state": "Uttar Pradesh", "lat": 28.5355, "lng": 77.3910},
    {"place_id": "in-ncr-cybercity", "name": "Cyber City", "city": "Gurugram", "state": "Haryana", "lat": 28.4949, "lng": 77.0895},
    # Hyderabad
    {"place_id": "in-hyd-gachibowli", "name": "Gachibowli", "city": "Hyderabad", "state": "Telangana", "lat": 17.4401, "lng": 78.3489},
    {"place_id": "in-hyd-hitec", "name": "HITEC City", "city": "Hyderabad", "state": "Telangana", "lat": 17.4435, "lng": 78.3772},
    {"place_id": "in-hyd-banjara", "name": "Banjara Hills", "city": "Hyderabad", "state": "Telangana", "lat": 17.4156, "lng": 78.4347},
    {"place_id": "in-hyd-jubilee", "name": "Jubilee Hills", "city": "Hyderabad", "state": "Telangana", "lat": 17.4325, "lng": 78.4071},
    {"place_id": "in-hyd-madhapur", "name": "Madhapur", "city": "Hyderabad", "state": "Telangana", "lat": 17.4483, "lng": 78.3915},
    {"place_id": "in-hyd-secunderabad", "name": "Secunderabad", "city": "Hyderabad", "state": "Telangana", "lat": 17.4399, "lng": 78.4983},
    {"place_id": "in-hyd-kondapur", "name": "Kondapur", "city": "Hyderabad", "state": "Telangana", "lat": 17.4615, "lng": 78.3639},
    # Pune
    {"place_id": "in-pnq-hinjewadi", "name": "Hinjewadi", "city": "Pune", "state": "Maharashtra", "lat": 18.5913, "lng": 73.7389},
    {"place_id": "in-pnq-kharadi", "name": "Kharadi", "city": "Pune", "state": "Maharashtra", "lat": 18.5515, "lng": 73.9410},
    {"place_id": "in-pnq-baner", "name": "Baner", "city": "Pune", "state": "Maharashtra", "lat": 18.5590, "lng": 73.7868},
    {"place_id": "in-pnq-vimannagar", "name": "Viman Nagar", "city": "Pune", "state": "Maharashtra", "lat": 18.5679, "lng": 73.9143},
    {"place_id": "in-pnq-koregaon", "name": "Koregaon Park", "city": "Pune", "state": "Maharashtra", "lat": 18.5362, "lng": 73.8939},
    {"place_id": "in-pnq-hadapsar", "name": "Hadapsar", "city": "Pune", "state": "Maharashtra", "lat": 18.5089, "lng": 73.9260},
    # Chennai
    {"place_id": "in-maa-tnagar", "name": "T Nagar", "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0418, "lng": 80.2341},
    {"place_id": "in-maa-adyar", "name": "Adyar", "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0012, "lng": 80.2565},
    {"place_id": "in-maa-velachery", "name": "Velachery", "city": "Chennai", "state": "Tamil Nadu", "lat": 12.9791, "lng": 80.2210},
    {"place_id": "in-maa-annanagar", "name": "Anna Nagar", "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0850, "lng": 80.2101},
    {"place_id": "in-maa-guindy", "name": "Guindy", "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0067, "lng": 80.2206},
    # Kolkata
    {"place_id": "in-ccu-saltlake", "name": "Salt Lake", "city": "Kolkata", "state": "West Bengal", "lat": 22.5867, "lng": 88.4171},
    {"place_id": "in-ccu-parkstreet", "name": "Park Street", "city": "Kolkata", "state": "West Bengal", "lat": 22.5525, "lng": 88.3520},
    {"place_id": "in-ccu-newtown", "name": "New Town", "city": "Kolkata", "state": "West Bengal", "lat": 22.5800, "lng": 88.4600},
]

# Give every locality a consistent address + place_type without repeating it above.
for _loc in INDIA_LOCALITIES:
    _loc.setdefault("place_type", "locality")
    _loc.setdefault("address", f"{_loc['name']}, {_loc['city']}, {_loc['state']}, India")

INDIA_PLACES = INDIA_PLACES + INDIA_LOCALITIES

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
