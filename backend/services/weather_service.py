"""
weather_service.py
Fetches real-time weather conditions from Open-Meteo Weather API.
No API key required.
https://api.open-meteo.com/v1/forecast
"""

import requests
from datetime import datetime
from typing import Dict

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10

_DIRS = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
         "S","SSW","SW","WSW","W","WNW","NW","NNW"]

def _deg_to_compass(deg: float) -> str:
    if deg is None:
        return "N/A"
    idx = round(deg / 22.5) % 16
    return _DIRS[idx]


def get_weather(lat: float, lon: float) -> Dict:
    try:
        resp = requests.get(
            WEATHER_URL,
            params={
                "latitude":  lat,
                "longitude": lon,
                "current": ",".join([
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "dew_point_2m",
                    "surface_pressure",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "visibility",
                    "uv_index",
                    "weather_code",
                ]),
                "daily": "sunrise,sunset",
                "timezone": "auto",
                "forecast_days": 1,
                "wind_speed_unit": "kmh",
            },
            timeout=TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        raise RuntimeError("Weather API timed out.")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Weather API error: {e}")

    cur   = data.get("current", {})
    daily = data.get("daily", {})

    sunrise_raw = (daily.get("sunrise") or [""])[0]
    sunset_raw  = (daily.get("sunset")  or [""])[0]

    def _fmt(raw: str) -> str:
        try:
            return datetime.fromisoformat(raw).strftime("%I:%M %p")
        except Exception:
            return raw or "N/A"

    vis_m  = cur.get("visibility")
    vis_km = round(vis_m / 1000, 2) if vis_m is not None else None

    uv = cur.get("uv_index")
    if uv is None:
        uv_cat = "Moderate"
    elif uv < 3:
        uv_cat = "Low"
    elif uv < 6:
        uv_cat = "Moderate"
    elif uv < 8:
        uv_cat = "High"
    elif uv < 11:
        uv_cat = "Very High"
    else:
        uv_cat = "Extreme"

    wind_speed = cur.get("wind_speed_10m")
    wind_deg = cur.get("wind_direction_10m")

    return {
        "temperature":        round(cur.get("temperature_2m", 0), 1) if cur.get("temperature_2m") is not None else None,
        "feels_like":         cur.get("apparent_temperature"),
        "humidity":           round(cur.get("relative_humidity_2m", 0)) if cur.get("relative_humidity_2m") is not None else None,
        "dew_point":          round(cur.get("dew_point_2m", 0)) if cur.get("dew_point_2m") is not None else None,
        "pressure":           round(cur.get("surface_pressure", 0), 1) if cur.get("surface_pressure") is not None else None,
        "wind":               round(wind_speed, 1) if wind_speed is not None else None,
        "wind_speed_kmh":     round(wind_speed) if wind_speed is not None else None,
        "wind_deg":           wind_deg,
        "wind_direction":     _deg_to_compass(wind_deg),
        "visibility":         vis_km,
        "uv_index":           uv,
        "uv_category":        uv_cat,
        "sunrise":            _fmt(sunrise_raw),
        "sunset":             _fmt(sunset_raw),
        "data_source":        "Open-Meteo",
    }
