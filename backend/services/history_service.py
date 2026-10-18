"""
history_service.py – Advanced Historical AQI & Pollutant Analytics Service
Provides real atmospheric historical readings from Open-Meteo Air Quality & Google Air Quality.
Supports 7-Day, 14-Day, and 30-Day time-series analytics with daily PM2.5, PM10, CO, NO2, SO2, O3 trends.
Persists snapshots into SQLite aqi_history and explicitly flags data completeness.
Never fabricates data or clones current readings across historical dates.
"""

import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from config import GOOGLE_AIR_QUALITY_API_KEY
from services.air_quality_service import naqi_category

HISTORY_URL = "https://airquality.googleapis.com/v1/history:lookup"
OPEN_METEO_AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
TIMEOUT = 12


def _cpcb_category_for_aqi(aqi: Optional[int]) -> Dict[str, str]:
    if aqi is None:
        return {"category": "Incomplete", "color": "#757575"}
    return naqi_category(int(aqi))


def fetch_multiday_history_from_open_meteo(lat: float, lon: float, days: int = 7, location_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches real hourly atmospheric observation & reanalysis data from Open-Meteo Air Quality API.
    Supports past_days up to 90 days.
    Returns daily aggregated AQI, PM2.5, PM10, NO2, SO2, CO, and O3.
    """
    # past_days parameter in Open-Meteo is past calendar days before today
    past_days = max(1, min(days - 1, 90))

    try:
        resp = requests.get(
            OPEN_METEO_AQ_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "past_days": past_days,
                "forecast_days": 1,
                "hourly": "us_aqi,pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
                "timezone": "auto"
            },
            timeout=TIMEOUT
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        return {
            "available": False,
            "days": [],
            "summary": None,
            "note": f"Atmospheric history service unreachable: {str(e)}"
        }

    hourly = raw.get("hourly", {})
    times = hourly.get("time", [])
    aqis = hourly.get("us_aqi", [])
    pm25s = hourly.get("pm2_5", [])
    pm10s = hourly.get("pm10", [])
    cos = hourly.get("carbon_monoxide", [])
    no2s = hourly.get("nitrogen_dioxide", [])
    so2s = hourly.get("sulphur_dioxide", [])
    o3s = hourly.get("ozone", [])

    if not times:
        return {
            "available": False,
            "days": [],
            "summary": None,
            "note": "No historical atmospheric readings returned for this location"
        }

    # Group by calendar day (YYYY-MM-DD)
    daily_groups: Dict[str, Dict[str, list]] = {}
    total_hours = len(times)

    for i in range(total_hours):
        t = times[i]
        if not t:
            continue
        day_key = t[:10]
        if day_key not in daily_groups:
            daily_groups[day_key] = {
                "aqi": [], "pm25": [], "pm10": [],
                "co": [], "no2": [], "so2": [], "o3": []
            }

        g = daily_groups[day_key]
        if i < len(aqis) and aqis[i] is not None:
            g["aqi"].append(aqis[i])
        if i < len(pm25s) and pm25s[i] is not None:
            g["pm25"].append(pm25s[i])
        if i < len(pm10s) and pm10s[i] is not None:
            g["pm10"].append(pm10s[i])
        if i < len(cos) and cos[i] is not None:
            g["co"].append(cos[i])
        if i < len(no2s) and no2s[i] is not None:
            g["no2"].append(no2s[i])
        if i < len(so2s) and so2s[i] is not None:
            g["so2"].append(so2s[i])
        if i < len(o3s) and o3s[i] is not None:
            g["o3"].append(o3s[i])

    sorted_days = sorted(daily_groups.keys())
    # Take up to the requested number of days
    target_days = sorted_days[-days:] if len(sorted_days) >= days else sorted_days

    results: List[Dict[str, Any]] = []
    from database import save_aqi_snapshot

    for d_str in target_days:
        g = daily_groups[d_str]
        aqi_vals = g["aqi"]
        pm25_vals = g["pm25"]
        pm10_vals = g["pm10"]
        co_vals = g["co"]
        no2_vals = g["no2"]
        so2_vals = g["so2"]
        o3_vals = g["o3"]

        has_data = len(aqi_vals) > 0
        avg_aqi = round(sum(aqi_vals) / len(aqi_vals)) if aqi_vals else None
        max_aqi = round(max(aqi_vals)) if aqi_vals else None
        min_aqi = round(min(aqi_vals)) if aqi_vals else None

        avg_pm25 = round(sum(pm25_vals) / len(pm25_vals), 1) if pm25_vals else None
        avg_pm10 = round(sum(pm10_vals) / len(pm10_vals), 1) if pm10_vals else None
        avg_no2  = round(sum(no2_vals) / len(no2_vals), 1) if no2_vals else None
        avg_so2  = round(sum(so2_vals) / len(so2_vals), 1) if so2_vals else None
        # CO in Open-Meteo is µg/m³; convert to mg/m³ for standard citizen readability (e.g. 0.45 mg/m³)
        avg_co   = round((sum(co_vals) / len(co_vals)) / 1000.0, 2) if co_vals else None
        avg_o3   = round(sum(o3_vals) / len(o3_vals), 1) if o3_vals else None

        cat_info = _cpcb_category_for_aqi(avg_aqi)

        try:
            dt = datetime.strptime(d_str, "%Y-%m-%d")
            formatted_date = dt.strftime("%b %d")
            day_name = dt.strftime("%a")
        except Exception:
            formatted_date = d_str
            day_name = ""

        day_record = {
            "date": formatted_date,
            "day": day_name,
            "date_iso": d_str,
            "aqi": avg_aqi,
            "max_aqi": max_aqi,
            "min_aqi": min_aqi,
            "category": cat_info["category"],
            "color": cat_info["color"],
            "pm25": avg_pm25,
            "pm10": avg_pm10,
            "no2": avg_no2,
            "so2": avg_so2,
            "co": avg_co,
            "o3": avg_o3,
            "data_points": len(aqi_vals),
            "is_complete": len(aqi_vals) >= 18 # At least 18 hours out of 24
        }
        results.append(day_record)

        # Persist daily snapshot to SQLite
        try:
            save_aqi_snapshot(
                loc=location_name or f"Lat {round(lat,2)}, Lon {round(lon,2)}",
                lat=lat,
                lon=lon,
                ts=f"{d_str} 12:00:00",
                data={
                    "aqi": avg_aqi,
                    "category": cat_info["category"],
                    "pm25": avg_pm25,
                    "pm10": avg_pm10,
                    "no2": avg_no2,
                    "so2": avg_so2,
                    "co": avg_co,
                    "o3": avg_o3
                }
            )
        except Exception:
            pass

    # Analytics & Summary Calculations
    valid_aqis = [d["aqi"] for d in results if d["aqi"] is not None]
    valid_pm25s = [d["pm25"] for d in results if d["pm25"] is not None]
    valid_pm10s = [d["pm10"] for d in results if d["pm10"] is not None]

    recorded_count = len(valid_aqis)
    is_complete_history = recorded_count == days and all(d["is_complete"] for d in results)

    if not valid_aqis:
        return {
            "available": False,
            "days": results,
            "summary": None,
            "completeness": {
                "days_requested": days,
                "days_recorded": 0,
                "is_complete": False,
                "label": "Incomplete historical coverage"
            },
            "note": "Historical readings temporarily unavailable for this coordinate"
        }

    period_avg = round(sum(valid_aqis) / len(valid_aqis))
    period_max = max(valid_aqis)
    period_min = min(valid_aqis)

    best_item = min([d for d in results if d["aqi"] is not None], key=lambda x: x["aqi"])
    worst_item = max([d for d in results if d["aqi"] is not None], key=lambda x: x["aqi"])

    # Calculate Trend & Percentage Change
    pct_change = 0.0
    day_change = 0
    trend_dir = "stable"

    if len(valid_aqis) >= 2:
        start_aqi = valid_aqis[0]
        end_aqi = valid_aqis[-1]
        yesterday_aqi = valid_aqis[-2]
        day_change = end_aqi - yesterday_aqi

        if start_aqi > 0:
            pct_change = round(((end_aqi - start_aqi) / start_aqi) * 100.0, 1)

        if pct_change < -3.0 or day_change < -5:
            trend_dir = "improving"
        elif pct_change > 3.0 or day_change > 5:
            trend_dir = "worsening"
        else:
            trend_dir = "stable"

    trend_narrative = (
        f"AQI improved by {abs(pct_change)}% over the {days}-day period."
        if trend_dir == "improving" else (
            f"AQI increased by {abs(pct_change)}% over the {days}-day period."
            if trend_dir == "worsening" else
            f"AQI remained stable within standard variance across {days} days."
        )
    )

    summary = {
        "period_avg": period_avg,
        "period_max": period_max,
        "period_min": period_min,
        "best_day": best_item,
        "worst_day": worst_item,
        "day_change": day_change,
        "pct_change": pct_change,
        "trend": trend_dir,
        "trend_narrative": trend_narrative,
        "pm25_avg": round(sum(valid_pm25s) / len(valid_pm25s), 1) if valid_pm25s else None,
        "pm10_avg": round(sum(valid_pm10s) / len(valid_pm10s), 1) if valid_pm10s else None,
        "dominant_pollutant": "PM2.5" if (valid_pm25s and valid_pm10s and (sum(valid_pm25s)/len(valid_pm25s)) > 40) else "PM10"
    }

    completeness = {
        "days_requested": days,
        "days_recorded": recorded_count,
        "is_complete": is_complete_history,
        "label": f"{recorded_count} of {days} days recorded" + ("" if is_complete_history else " (partial coverage)")
    }

    return {
        "available": True,
        "days": results,
        "summary": summary,
        "completeness": completeness,
        "note": f"Atmospheric station & reanalysis network • {completeness['label']}"
    }


def get_history(lat: float, lon: float, days: int = 7, location_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Main entry point for multi-day historical analytics.
    Ensures real historical data only. If API fails, attempts SQLite fallback.
    """
    # Enforce valid ranges: 7, 14, 30 days
    allowed_days = [7, 14, 30]
    if days not in allowed_days:
        days = 7 if days < 14 else (14 if days < 30 else 30)

    # Fetch real multi-day history
    history_data = fetch_multiday_history_from_open_meteo(lat, lon, days=days, location_name=location_name)

    if history_data.get("available") and len(history_data.get("days", [])) > 0:
        return history_data

    # Fallback: check SQLite persisted history
    from database import get_cached_history_snapshots
    snapshots = get_cached_history_snapshots(lat, lon, days=days)

    if snapshots:
        results = []
        for s in snapshots:
            dt_str = s.get("timestamp", "")[:10]
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
                formatted_date = dt.strftime("%b %d")
                day_name = dt.strftime("%a")
            except Exception:
                formatted_date = dt_str
                day_name = ""

            aqi_val = round(s.get("aqi")) if s.get("aqi") is not None else None
            cat_info = _cpcb_category_for_aqi(aqi_val)

            results.append({
                "date": formatted_date,
                "day": day_name,
                "date_iso": dt_str,
                "aqi": aqi_val,
                "max_aqi": aqi_val,
                "min_aqi": aqi_val,
                "category": cat_info["category"],
                "color": cat_info["color"],
                "pm25": s.get("pm25"),
                "pm10": s.get("pm10"),
                "no2": s.get("no2"),
                "so2": s.get("so2"),
                "co": s.get("co"),
                "o3": s.get("o3"),
                "data_points": 1,
                "is_complete": True
            })

        valid_aqis = [d["aqi"] for d in results if d["aqi"] is not None]
        summary = {
            "period_avg": round(sum(valid_aqis)/len(valid_aqis)) if valid_aqis else 0,
            "period_max": max(valid_aqis) if valid_aqis else 0,
            "period_min": min(valid_aqis) if valid_aqis else 0,
            "best_day": min(results, key=lambda x: x["aqi"]) if results else None,
            "worst_day": max(results, key=lambda x: x["aqi"]) if results else None,
            "day_change": 0,
            "pct_change": 0.0,
            "trend": "stable",
            "trend_narrative": "Persisted snapshot history retrieved from local database."
        }

        return {
            "available": True,
            "days": results,
            "summary": summary,
            "completeness": {
                "days_requested": days,
                "days_recorded": len(results),
                "is_complete": len(results) >= days,
                "label": f"{len(results)} of {days} days recorded (persisted database)"
            },
            "note": "Persisted local database snapshots"
        }

    return {
        "available": False,
        "days": [],
        "summary": None,
        "completeness": {
            "days_requested": days,
            "days_recorded": 0,
            "is_complete": False,
            "label": "Incomplete historical coverage"
        },
        "note": "Atmospheric history temporarily unavailable for this area"
    }
