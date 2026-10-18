"""
geocoding_service.py
Resolves any Indian location (locality, area, town, village, city, district, pincode, municipal ward)
to latitude and longitude using verified directory mapping, Open-Meteo, and OpenStreetMap Nominatim.
"""

import time
import requests
from typing import List, Dict, Optional

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT = 4

# In-memory LRU-like cache for search and reverse geocode
_GEO_CACHE: Dict[str, Dict] = {}
_GEO_CACHE_TTL = 3600  # 1 hour

def _get_cached_geo(key: str):
    entry = _GEO_CACHE.get(key)
    if entry and (time.time() - entry["ts"] < _GEO_CACHE_TTL):
        return entry["data"]
    return None

def _set_cached_geo(key: str, data):
    if len(_GEO_CACHE) > 500:
        sorted_keys = sorted(_GEO_CACHE.keys(), key=lambda k: _GEO_CACHE[k]["ts"])
        for k in sorted_keys[:100]:
            _GEO_CACHE.pop(k, None)
    _GEO_CACHE[key] = {"ts": time.time(), "data": data}
    return data

# Verified directory of Mumbai municipal wards and prominent localities for instant, accurate matching
MUMBAI_WARDS_AND_LOCALITIES = [
    {
        "name": "Ward F/North (Wadala / CGS Colony)",
        "locality": "CGS Colony, Wadala",
        "city": "Mumbai",
        "district": "Mumbai City",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.0222,
        "longitude": 72.8681,
        "elevation": 8,
        "display_name": "Ward F/North (CGS Colony, Wadala, Antop Hill, Matunga East), Mumbai, Maharashtra, India",
        "keywords": ["cgs colony", "f/north", "fn ward", "f north", "ward f/north", "ward f north", "antop hill", "wadala east", "gtb nagar", "koliwada", "pratiksha nagar"]
    },
    {
        "name": "Ward F/South (Parel / Sewri)",
        "locality": "Parel",
        "city": "Mumbai",
        "district": "Mumbai City",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 18.9950,
        "longitude": 72.8420,
        "elevation": 10,
        "display_name": "Ward F/South (Parel, Sewri, Lalbaug, Naigaon), Mumbai, Maharashtra, India",
        "keywords": ["f/south", "fs ward", "f south", "ward f/south", "ward f south", "parel", "sewri", "lalbaug", "naigaon", "currey road", "hindmata"]
    },
    {
        "name": "Ward K/West (Andheri West / Versova)",
        "locality": "Andheri West",
        "city": "Mumbai",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.1250,
        "longitude": 72.8250,
        "elevation": 12,
        "display_name": "Ward K/West (Andheri West, Versova, Juhu, Oshiwara, Lokhandwala), Mumbai, Maharashtra, India",
        "keywords": ["k/west", "kw ward", "k west", "ward k/west", "ward k west", "andheri west", "versova", "juhu", "oshiwara", "lokhandwala", "vile parle west"]
    },
    {
        "name": "Ward K/East (Andheri East / Marol)",
        "locality": "Andheri East",
        "city": "Mumbai",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.1170,
        "longitude": 72.8690,
        "elevation": 15,
        "display_name": "Ward K/East (Andheri East, Jogeshwari East, Marol, SEEPZ, Chakala), Mumbai, Maharashtra, India",
        "keywords": ["k/east", "ke ward", "k east", "ward k/east", "ward k east", "andheri east", "marol", "seepz", "jogeshwari east", "chakala", "sakinaka"]
    },
    {
        "name": "Ward H/West (Bandra West / Khar)",
        "locality": "Bandra West",
        "city": "Mumbai",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.0583,
        "longitude": 72.8303,
        "elevation": 9,
        "display_name": "Ward H/West (Bandra West, Khar West, Santacruz West, Bandstand, Pali Hill), Mumbai, Maharashtra, India",
        "keywords": ["h/west", "hw ward", "h west", "ward h/west", "ward h west", "bandra west", "khar west", "santacruz west", "bandstand", "pali hill", "carter road"]
    },
    {
        "name": "Ward H/East (Bandra East / BKC)",
        "locality": "Bandra East",
        "city": "Mumbai",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.0600,
        "longitude": 72.8550,
        "elevation": 11,
        "display_name": "Ward H/East (Bandra East, Bandra Kurla Complex - BKC, Kalina, Santacruz East), Mumbai, Maharashtra, India",
        "keywords": ["h/east", "he ward", "h east", "ward h/east", "ward h east", "bandra east", "bkc", "bandra kurla complex", "kalina", "santacruz east"]
    },
    {
        "name": "Ward A (Colaba / Fort / Nariman Point)",
        "locality": "Colaba",
        "city": "Mumbai",
        "district": "Mumbai City",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 18.9220,
        "longitude": 72.8330,
        "elevation": 7,
        "display_name": "Ward A (Colaba, Fort, Nariman Point, Churchgate, Cuffe Parade), Mumbai, Maharashtra, India",
        "keywords": ["ward a", "colaba", "fort", "nariman point", "churchgate", "cuffe parade", "marine lines", "ballard estate"]
    },
    {
        "name": "Ward G/South (Worli / Lower Parel)",
        "locality": "Worli",
        "city": "Mumbai",
        "district": "Mumbai City",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.0060,
        "longitude": 72.8180,
        "elevation": 8,
        "display_name": "Ward G/South (Worli, Lower Parel, Prabhadevi, Mahalaxmi), Mumbai, Maharashtra, India",
        "keywords": ["g/south", "gs ward", "g south", "ward g/south", "ward g south", "worli", "lower parel", "prabhadevi", "mahalaxmi"]
    },
    {
        "name": "Ward G/North (Dadar / Dharavi / Mahim)",
        "locality": "Dadar",
        "city": "Mumbai",
        "district": "Mumbai City",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.0178,
        "longitude": 72.8478,
        "elevation": 9,
        "display_name": "Ward G/North (Dadar West, Dharavi, Mahim), Mumbai, Maharashtra, India",
        "keywords": ["g/north", "gn ward", "g north", "ward g/north", "ward g north", "dadar", "dharavi", "mahim", "dadar west"]
    },
    {
        "name": "Ward L (Kurla)",
        "locality": "Kurla",
        "city": "Mumbai",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.0700,
        "longitude": 72.8800,
        "elevation": 10,
        "display_name": "Ward L (Kurla West, Kurla East, Chunabhatti), Mumbai, Maharashtra, India",
        "keywords": ["ward l", "kurla", "kurla west", "kurla east", "chunabhatti"]
    },
    {
        "name": "Ward N (Ghatkopar)",
        "locality": "Ghatkopar",
        "city": "Mumbai",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.0860,
        "longitude": 72.9080,
        "elevation": 12,
        "display_name": "Ward N (Ghatkopar West, Ghatkopar East, Pant Nagar), Mumbai, Maharashtra, India",
        "keywords": ["ward n", "ghatkopar", "ghatkopar west", "ghatkopar east", "pant nagar"]
    },
    {
        "name": "Ward P/South (Goregaon)",
        "locality": "Goregaon",
        "city": "Mumbai",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.1646,
        "longitude": 72.8493,
        "elevation": 14,
        "display_name": "Ward P/South (Goregaon West, Goregaon East, Aarey Colony), Mumbai, Maharashtra, India",
        "keywords": ["p/south", "ps ward", "p south", "ward p/south", "ward p south", "goregaon", "goregaon west", "goregaon east", "aarey colony"]
    },
    {
        "name": "Ward P/North (Malad)",
        "locality": "Malad",
        "city": "Mumbai",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.1860,
        "longitude": 72.8485,
        "elevation": 12,
        "display_name": "Ward P/North (Malad West, Malad East, Marve), Mumbai, Maharashtra, India",
        "keywords": ["p/north", "pn ward", "p north", "ward p/north", "ward p north", "malad", "malad west", "malad east", "marve"]
    },
    {
        "name": "Ward R/Central (Borivali)",
        "locality": "Borivali",
        "city": "Mumbai",
        "district": "Mumbai Suburban",
        "state": "Maharashtra",
        "country": "India",
        "country_code": "IN",
        "latitude": 19.2300,
        "longitude": 72.8560,
        "elevation": 15,
        "display_name": "Ward R/Central (Borivali West, Borivali East, Gorai), Mumbai, Maharashtra, India",
        "keywords": ["r/central", "rc ward", "r central", "ward r/central", "ward r central", "borivali", "borivali west", "borivali east", "gorai"]
    }
]


def search_locations(query: str, count: int = 5) -> List[Dict]:
    """
    Returns candidate locations for a query string.
    Each result contains: name, locality, city, district, state, country,
    latitude, longitude, display_name.
    """
    q_clean = query.strip()
    if not q_clean:
        return []

    cache_k = f"q:{q_clean.lower()}:{count}"
    cached = _get_cached_geo(cache_k)
    if cached is not None:
        return cached

    results: List[Dict] = []
    q_lower = q_clean.lower()

    # 1. Quick match against verified Mumbai wards and prominent localities
    local_matches = []
    for entry in MUMBAI_WARDS_AND_LOCALITIES:
        for kw in entry["keywords"]:
            if kw in q_lower or (len(q_lower) >= 3 and q_lower in kw):
                match_copy = {k: v for k, v in entry.items() if k != "keywords"}
                local_matches.append(match_copy)
                break
    if local_matches:
        results.extend(local_matches[:count])

    # If local matches already satisfy count, cache and return
    if len(results) >= count:
        _set_cached_geo(cache_k, results[:count])
        return results[:count]

    # 2. Query Open-Meteo Geocoding API
    try:
        resp = requests.get(
            GEOCODING_URL,
            params={"name": q_clean, "count": count, "format": "json", "language": "en"},
            timeout=TIMEOUT
        )
        if resp.ok:
            data = resp.json()
            results_raw = data.get("results", [])
            for r in results_raw:
                name = r.get("name", "")
                admin2 = r.get("admin2", "")
                admin1 = r.get("admin1", "")
                country = r.get("country", "")

                parts = [name]
                if admin2 and admin2 != name:
                    parts.append(admin2)
                if admin1 and admin1 not in parts:
                    parts.append(admin1)
                if country and country not in parts:
                    parts.append(country)

                display = ", ".join(p for p in parts if p)
                city_name = admin2 or (name if name.lower() in ["mumbai", "delhi", "bengaluru", "pune", "hyderabad", "chennai", "kolkata"] else admin1)

                candidate = {
                    "name":         name,
                    "locality":     name,
                    "city":         city_name,
                    "district":     admin2 or city_name,
                    "state":        admin1,
                    "country":      country,
                    "country_code": r.get("country_code", ""),
                    "latitude":     r.get("latitude"),
                    "longitude":    r.get("longitude"),
                    "elevation":    r.get("elevation", 0),
                    "display_name": display,
                }
                # Avoid duplicates
                if not any(abs(c["latitude"] - candidate["latitude"]) < 0.01 and abs(c["longitude"] - candidate["longitude"]) < 0.01 for c in results):
                    results.append(candidate)
    except Exception as e:
        print(f"[Geocoding] Open-Meteo notice: {e}")

    # 3. Fall back to OpenStreetMap Nominatim if results are sparse or query contains wards/colonies
    if len(results) < count:
        try:
            nom_query = q_clean
            if "ward" in q_lower and "mumbai" not in q_lower:
                nom_query = f"{q_clean}, Mumbai"

            nom_resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": nom_query, "format": "json", "countrycodes": "in", "limit": count, "addressdetails": 1},
                headers={"User-Agent": "SkyCheckApp/1.0 (AirGuard-AQI-Tracker)"},
                timeout=TIMEOUT
            )
            if nom_resp.ok:
                nom_data = nom_resp.json()
                for item in nom_data:
                    addr = item.get("address", {})
                    first_part = item.get("display_name", "").split(",")[0].strip()
                    name = item.get("name") or first_part or addr.get("suburb") or addr.get("neighbourhood") or q_clean
                    city = addr.get("city") or addr.get("town") or addr.get("municipality") or addr.get("state_district") or ""
                    state = addr.get("state", "")
                    country = addr.get("country", "India")
                    lat_f = float(item.get("lat"))
                    lon_f = float(item.get("lon"))

                    candidate = {
                        "name":         name,
                        "locality":     name,
                        "city":         city,
                        "district":     addr.get("county", city),
                        "state":        state,
                        "country":      country,
                        "country_code": "IN",
                        "latitude":     lat_f,
                        "longitude":    lon_f,
                        "elevation":    0,
                        "display_name": item.get("display_name", f"{name}, {city}"),
                    }
                    if not any(abs(c["latitude"] - candidate["latitude"]) < 0.01 and abs(c["longitude"] - candidate["longitude"]) < 0.01 for c in results):
                        results.append(candidate)
        except Exception as e:
            print(f"[Geocoding] Nominatim fallback notice: {e}")

    final_results = results[:count]
    _set_cached_geo(cache_k, final_results)
    return final_results


def resolve_single(query: str) -> Optional[Dict]:
    results = search_locations(query, count=1)
    return results[0] if results else None


def reverse_geocode(lat: float, lon: float) -> Dict:
    """
    Reverse geocodes latitude and longitude into an official locality object.
    Uses OpenStreetMap Nominatim with a structured fallback.
    """
    cache_k = f"rev:{round(lat, 4)}:{round(lon, 4)}"
    cached = _get_cached_geo(cache_k)
    if cached is not None:
        return cached

    # Check proximity to known Mumbai wards
    for entry in MUMBAI_WARDS_AND_LOCALITIES:
        if abs(entry["latitude"] - lat) < 0.015 and abs(entry["longitude"] - lon) < 0.015:
            res = {k: v for k, v in entry.items() if k != "keywords"}
            res["is_live_gps"] = True
            _set_cached_geo(cache_k, res)
            return res

    try:
        nom_resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "addressdetails": 1,
                "zoom": 16
            },
            headers={"User-Agent": "SkyCheckApp/1.0 (AirGuard-AQI-Tracker)"},
            timeout=TIMEOUT
        )
        if nom_resp.ok:
            data = nom_resp.json()
            addr = data.get("address", {})

            name_candidates = [
                addr.get("suburb"),
                addr.get("neighbourhood"),
                addr.get("residential"),
                addr.get("quarter"),
                addr.get("village"),
                addr.get("town"),
                addr.get("city_district"),
                addr.get("city"),
                data.get("name")
            ]
            primary_name = next((c for c in name_candidates if c), None)

            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("municipality")
                or addr.get("city_district")
                or addr.get("state_district")
                or ""
            )

            if not primary_name:
                primary_name = city or f"Location ({round(lat, 3)}, {round(lon, 3)})"

            state = addr.get("state", "")
            district = addr.get("state_district") or addr.get("county") or city
            country = addr.get("country", "India")
            country_code = addr.get("country_code", "in").upper()

            display = data.get("display_name") or f"{primary_name}, {city}, {state}"

            res = {
                "name":         primary_name,
                "locality":     primary_name,
                "city":         city,
                "district":     district,
                "state":        state,
                "country":      country,
                "country_code": country_code,
                "latitude":     round(lat, 5),
                "longitude":    round(lon, 5),
                "display_name": display,
                "is_live_gps":  True
            }
            _set_cached_geo(cache_k, res)
            return res
    except Exception as e:
        print(f"[Geocoding] Reverse geocode notice: {e}")

    # Graceful fallback when reverse service is unreachable
    coords_label = f"Location ({round(lat, 3)}°, {round(lon, 3)}°)"
    fallback_res = {
        "name":         coords_label,
        "locality":     coords_label,
        "city":         "",
        "district":     "",
        "state":        "",
        "country":      "India",
        "country_code": "IN",
        "latitude":     round(lat, 5),
        "longitude":    round(lon, 5),
        "display_name": f"{coords_label}, Live GPS Coordinates",
        "is_live_gps":  True
    }
    _set_cached_geo(cache_k, fallback_res)
    return fallback_res
