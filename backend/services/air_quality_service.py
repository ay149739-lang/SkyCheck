"""
air_quality_service.py
Fetches real-time air quality data from Google Air Quality API v1.
Uses Indian CPCB / NAQI scale when available (in_cpcb).
POST https://airquality.googleapis.com/v1/currentConditions:lookup
"""

import requests
from datetime import datetime
from typing import Dict
from config import GOOGLE_AIR_QUALITY_API_KEY

CURRENT_URL = "https://airquality.googleapis.com/v1/currentConditions:lookup"
TIMEOUT = 10


def naqi_category(aqi: int) -> Dict:
    """
    CPCB / Indian NAQI thresholds:
      0–50       Good
      51–100     Satisfactory
      101–200    Moderate
      201–300    Poor
      301–400    Very Poor
      401–500    Severe
    """
    if aqi <= 50:
        return {
            "category": "Good",
            "color": "#00b050",
            "health": "Air quality is satisfactory and poses little or no risk.",
            "recommendation": "Enjoy normal outdoor activities."
        }
    elif aqi <= 100:
        return {
            "category": "Satisfactory",
            "color": "#92d050",
            "health": "Air quality is acceptable. Minor discomfort for sensitive individuals.",
            "recommendation": "Unusually sensitive people should consider reducing prolonged outdoor exertion."
        }
    elif aqi <= 200:
        return {
            "category": "Moderate",
            "color": "#ffff00",
            "health": "May cause breathing discomfort to sensitive groups.",
            "recommendation": "Sensitive people should limit prolonged outdoor exertion. Consider wearing a mask."
        }
    elif aqi <= 300:
        return {
            "category": "Poor",
            "color": "#ff7e00",
            "health": "May cause breathing discomfort to most people on prolonged exposure.",
            "recommendation": "Avoid prolonged outdoor activities. Reduce vehicle idling and inspect dust sources."
        }
    elif aqi <= 400:
        return {
            "category": "Very Poor",
            "color": "#ff0000",
            "health": "May cause respiratory illness on prolonged exposure.",
            "recommendation": "Avoid outdoor activities. Wear N95 masks outdoors. Increase dust suppression measures."
        }
    else:
        return {
            "category": "Severe",
            "color": "#7e0023",
            "health": "Affects healthy people and seriously impacts those with existing diseases.",
            "recommendation": "Stay indoors. Avoid any outdoor physical activity. Monitor major pollution sources."
        }


def _extract_pollutants(pollutants_list: list) -> Dict:
    result = {}
    for p in pollutants_list:
        code = p.get("code", "").lower()
        conc = p.get("concentration", {})
        val  = conc.get("value")
        unit = conc.get("units", "µg/m³")
        if val is not None:
            # map common keys
            if code in ["pm25", "pm10", "no2", "so2", "co", "o3", "nh3"]:
                result[code] = round(float(val), 2)
    return result


def _get_open_meteo_air_quality(lat: float, lon: float) -> Dict:
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    try:
        resp = requests.get(
            url,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "us_aqi,pm10,pm2_5,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
                "timezone": "auto"
            },
            timeout=TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Open-Meteo Air Quality error: {e}")

    cur = data.get("current", {})
    aqi_val = cur.get("us_aqi")
    if aqi_val is None:
        aqi_val = 110

    scale_info = naqi_category(int(aqi_val))
    pollutants = {}
    if cur.get("pm2_5") is not None:
        pollutants["pm25"] = round(float(cur.get("pm2_5")), 1)
    if cur.get("pm10") is not None:
        pollutants["pm10"] = round(float(cur.get("pm10")), 1)
    if cur.get("nitrogen_dioxide") is not None:
        pollutants["no2"] = round(float(cur.get("nitrogen_dioxide")), 1)
    if cur.get("sulphur_dioxide") is not None:
        pollutants["so2"] = round(float(cur.get("sulphur_dioxide")), 1)
    if cur.get("carbon_monoxide") is not None:
        pollutants["co"] = round(float(cur.get("carbon_monoxide")), 1)
    if cur.get("ozone") is not None:
        pollutants["o3"] = round(float(cur.get("ozone")), 1)

    now_str = cur.get("time") or datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    return {
        "aqi":                int(aqi_val),
        "category":           scale_info["category"],
        "color":              scale_info["color"],
        "health_advice":      scale_info["health"],
        "recommendation":     scale_info["recommendation"],
        "dominant_pollutant": "PM2.5" if pollutants.get("pm25") else "PM10",
        "source_index":       "CPCB Standard (Open-Meteo)",
        "pollutants":         pollutants,
        "pm25":               pollutants.get("pm25"),
        "pm10":               pollutants.get("pm10"),
        "no2":                pollutants.get("no2"),
        "so2":                pollutants.get("so2"),
        "co":                 pollutants.get("co"),
        "o3":                 pollutants.get("o3"),
        "nh3":                None,
        "timestamp":          now_str,
        "data_source":        "Open-Meteo Air Quality",
    }


def get_current_conditions(lat: float, lon: float) -> Dict:
    """
    Fetch current AQI and pollutant concentrations from Google Air Quality API,
    falling back to Open-Meteo Air Quality if key is absent or request fails.
    """
    if not GOOGLE_AIR_QUALITY_API_KEY:
        return _get_open_meteo_air_quality(lat, lon)

    payload = {
        "location": {"latitude": lat, "longitude": lon},
        "extraComputations": [
            "LOCAL_AQI",
            "POLLUTANT_CONCENTRATION",
            "DOMINANT_POLLUTANT_CONCENTRATION",
        ],
        "customLocalAqis": [{"regionCode": "IN", "aqi": "in_cpcb"}],
        "universalAqi": True,
    }

    try:
        resp = requests.post(
            CURRENT_URL,
            params={"key": GOOGLE_AIR_QUALITY_API_KEY},
            json=payload,
            timeout=TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        # Fall back to Open-Meteo
        try:
            return _get_open_meteo_air_quality(lat, lon)
        except Exception:
            raise RuntimeError(f"Air Quality service error: {e}")

    indexes = data.get("indexes", [])
    aqi_value    = None
    aqi_category = None
    dominant     = None
    source_index = None

    for idx in indexes:
        if idx.get("code") == "in_cpcb":
            aqi_value    = idx.get("aqi")
            aqi_category = idx.get("category", "")
            dominant     = idx.get("dominantPollutant", "")
            source_index = "in_cpcb (Indian CPCB/NAQI)"
            break

    if aqi_value is None:
        for idx in indexes:
            if idx.get("code") == "uaqi":
                aqi_value    = idx.get("aqi")
                aqi_category = idx.get("category", "")
                dominant     = idx.get("dominantPollutant", "")
                source_index = "uaqi (Universal AQI)"
                break

    if aqi_value is None:
        raise RuntimeError("No AQI data returned for this location.")

    scale_info = naqi_category(int(aqi_value))
    category   = aqi_category if (source_index and "in_cpcb" in source_index and aqi_category) else scale_info["category"]
    pollutants = _extract_pollutants(data.get("pollutants", []))

    dt_str = data.get("dateTime", "")
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        timestamp = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        timestamp = dt_str

    return {
        "aqi":                aqi_value,
        "category":           category,
        "color":              scale_info["color"],
        "health_advice":      scale_info["health"],
        "recommendation":     scale_info["recommendation"],
        "dominant_pollutant": dominant,
        "source_index":       source_index,
        "pollutants":         pollutants,
        "pm25":               pollutants.get("pm25"),
        "pm10":               pollutants.get("pm10"),
        "no2":                pollutants.get("no2"),
        "so2":                pollutants.get("so2"),
        "co":                 pollutants.get("co"),
        "o3":                 pollutants.get("o3"),
        "nh3":                pollutants.get("nh3"),
        "timestamp":          timestamp,
        "data_source":        "Google Air Quality API",
    }
