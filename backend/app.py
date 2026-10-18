"""
app.py – SkyCheck Flask Backend API Server
Supports location resolution, real-time AQI, weather, multi-day historical analytics,
SQLite persistent logging, and location-aware citizen pollution complaint dispatch.

Routes:
  GET  /api/health
  GET  /api/location/search?q=&count=
  GET  /api/dashboard?location=&days=
  GET  /api/air-quality?lat=&lon=
  GET  /api/weather?lat=&lon=
  GET  /api/history?lat=&lon=&days=7
  GET  /api/authority?locality=&city=&district=&state=
  POST /api/complaints/submit
  POST /api/send-report (legacy alias)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from config import CACHE_TTL_SECONDS, google_aq_key_configured, smtp_configured
from database import (
    init_db, seed_authorities, save_search, save_aqi_snapshot, get_recent_email_reports,
    mask_email, hash_email, create_email_report, save_complaint
)
from services.geocoding_service import search_locations, resolve_single, reverse_geocode
from services.air_quality_service import get_current_conditions
from services.weather_service import get_weather
from services.history_service import get_history
from services.authority_service import resolve_authority_for_location, get_all_verified_authorities
from services.email_service import send_complaint, send_test_email, validate_complaint_payload, generate_reference_id

_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

app = Flask(__name__)
CORS(app, origins=["*"])

_CACHE: dict = {}

def _cache_key(*args) -> str:
    return "|".join(str(a) for a in args)

def _cached(key: str):
    entry = _CACHE.get(key)
    if entry and (time.time() - entry["ts"] < CACHE_TTL_SECONDS):
        return entry["data"]
    return None

def _store(key: str, data):
    _CACHE[key] = {"ts": time.time(), "data": data}
    return data


@app.route("/")
def home():
    if os.path.exists(os.path.join(_FRONTEND_DIR, "index.html")):
        return send_from_directory(_FRONTEND_DIR, "index.html")
    return jsonify({"name": "SkyCheck API", "status": "running"})


@app.route("/<path:filename>")
def static_files(filename):
    file_path = os.path.join(_FRONTEND_DIR, filename)
    if os.path.exists(file_path):
        return send_from_directory(_FRONTEND_DIR, filename)
    return jsonify({"error": f"File '{filename}' not found"}), 404


@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "email_mode": "live_smtp" if smtp_configured() else "development_test_mock",
        "google_aq_key": "configured" if google_aq_key_configured() else "using_open_meteo_atmospheric_network",
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "database": "sqlite_airguard_active"
    })


@app.route("/api/location/search")
def location_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Please enter a location to search."}), 400

    count = min(int(request.args.get("count", 5)), 10)
    cache_k = _cache_key("geo", q.lower(), count)
    cached = _cached(cache_k)
    if cached:
        return jsonify(cached)

    try:
        results = search_locations(q, count=count)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    if not results:
        return jsonify({"query": q, "results": [], "error": f"No locations found for '{q}'."}), 200

    data = {"query": q, "results": results}
    _store(cache_k, data)

    # Save to search_history table
    best = results[0]
    save_search(q, best.get("display_name"), best.get("latitude"), best.get("longitude"))

    return jsonify(data)


@app.route("/api/location/reverse")
def location_reverse():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "Provide valid lat and lon coordinates."}), 400

    cache_k = _cache_key("geo_rev", round(lat, 4), round(lon, 4))
    cached = _cached(cache_k)
    if cached:
        return jsonify(cached)

    loc = reverse_geocode(lat, lon)
    _store(cache_k, loc)
    return jsonify(loc)


@app.route("/api/air-quality")
def air_quality():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "Provide valid lat and lon parameters."}), 400

    location_name = request.args.get("location_name", "").strip() or f"Lat {round(lat, 3)}, Lon {round(lon, 3)}"
    force_refresh = request.args.get("refresh") in ["1", "true"]

    cache_k = _cache_key("aq", round(lat, 3), round(lon, 3))
    if not force_refresh:
        cached = _cached(cache_k)
        if cached:
            return jsonify(cached)

    try:
        data = get_current_conditions(lat, lon)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    _store(cache_k, data)

    # Persist live snapshot to SQLite
    try:
        save_aqi_snapshot(location_name, lat, lon, data.get("timestamp"), data)
    except Exception as e:
        print(f"[DB] Live snapshot save error: {e}")

    return jsonify(data)


@app.route("/api/weather")
def weather():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "Provide valid lat and lon parameters."}), 400

    force_refresh = request.args.get("refresh") in ["1", "true"]
    cache_k = _cache_key("wx", round(lat, 3), round(lon, 3))
    if not force_refresh:
        cached = _cached(cache_k)
        if cached:
            return jsonify(cached)

    try:
        data = get_weather(lat, lon)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    _store(cache_k, data)
    return jsonify(data)


@app.route("/api/history")
def history():
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "Provide valid lat and lon parameters."}), 400

    try:
        days = int(request.args.get("days", 7))
    except ValueError:
        days = 7

    force_refresh = request.args.get("refresh") in ["1", "true"]
    cache_k = _cache_key("hist", round(lat, 3), round(lon, 3), days)
    if not force_refresh:
        cached = _cached(cache_k)
        if cached:
            return jsonify(cached)

    location_name = request.args.get("location_name", "").strip() or None
    data = get_history(lat, lon, days, location_name=location_name)
    _store(cache_k, data)
    return jsonify(data)


@app.route("/api/authority")
def authority():
    locality = request.args.get("locality", "").strip()
    city     = request.args.get("city", "").strip()
    district = request.args.get("district", "").strip()
    state    = request.args.get("state", "").strip()
    disp     = request.args.get("display_name", "").strip()

    auth = resolve_authority_for_location(
        locality=locality,
        city=city,
        district=district,
        state=state,
        display_name=disp
    )
    return jsonify(auth)


@app.route("/api/authorities")
def list_authorities():
    """Returns the list of all authorities from the verified directory."""
    authorities = get_all_verified_authorities()
    return jsonify({"success": True, "authorities": authorities, "count": len(authorities)})


@app.route("/api/dashboard")
def dashboard():
    loc_query = request.args.get("location", "").strip()
    if not loc_query:
        return jsonify({"error": "Provide location parameter."}), 400

    try:
        days = int(request.args.get("days", 7))
    except ValueError:
        days = 7

    try:
        loc = resolve_single(loc_query)
        if not loc:
            return jsonify({"error": f"Location '{loc_query}' not found."}), 404

        lat = loc["latitude"]
        lon = loc["longitude"]

        aq_data   = get_current_conditions(lat, lon)
        wx_data   = get_weather(lat, lon)
        hist_data = get_history(lat, lon, days=days)
        auth_data = resolve_authority_for_location(
            locality=loc.get("locality") or loc.get("name") or "",
            city=loc.get("city") or "",
            district=loc.get("district") or "",
            state=loc.get("state") or "",
            display_name=loc.get("display_name") or ""
        )

        # Save snapshot to database
        save_aqi_snapshot(loc.get("display_name", loc_query), lat, lon, aq_data.get("timestamp"), aq_data)

        return jsonify({
            "location": loc,
            "air_quality": aq_data,
            "weather": wx_data,
            "history": hist_data,
            "authority": auth_data,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/complaints/submit", methods=["POST"])
def submit_complaint():
    """
    Submits a location-aware environmental complaint to the responsible government authority.
    Validates input, rate limits, anti-abuse, resolves recipient via verified backend directory,
    and returns transparent delivery confirmation.
    """
    body = request.get_json(silent=True) or {}

    # Validate payload
    is_valid, error_msg = validate_complaint_payload(body)
    if not is_valid:
        return jsonify({"success": False, "message": error_msg}), 400

    user_email = body.get("user_email")
    location   = body.get("location") or {}
    aqi_data   = body.get("air_quality") or body.get("aqi_data") or {}
    weather    = body.get("weather") or {}
    desc       = body.get("description", "").strip()
    source     = body.get("pollution_source", "General")
    photo_b64  = body.get("photo_evidence")

    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    result = send_complaint(
        user_email=user_email,
        location=location,
        aqi_data=aqi_data,
        weather_data=weather,
        complaint_description=desc,
        pollution_source=source,
        photo_data_base64=photo_b64,
        client_ip=client_ip
    )

    status_code = 200 if result.get("success") else 400
    if result.get("error_code") in ["RATE_LIMIT_EXCEEDED", "DUPLICATE_SUBMISSION"]:
        status_code = 429
    elif result.get("error_code") == "SMTP_NOT_CONFIGURED":
        status_code = 503
    elif result.get("error_code") == "SMTP_DELIVERY_FAILED":
        status_code = 502

    return jsonify(result), status_code


@app.route("/api/complaints/record-draft", methods=["POST"])
def record_complaint_draft():
    """
    Records a generated citizen complaint draft in SQLite audit logs.
    Preserves audit history for user-driven mailto complaints without requiring SMTP credentials.
    """
    body = request.get_json(silent=True) or {}
    user_name = (body.get("user_name") or "").strip()
    user_email = (body.get("user_email") or "").strip()
    loc = body.get("location") or {}
    loc_name = loc.get("name") or loc.get("locality") or body.get("location_name") or "Reported Location"
    desc = (body.get("description") or "").strip()
    source = body.get("pollution_source") or "General"
    auth_name = body.get("authority_name") or "Environmental Authority"
    recipient_email = (body.get("recipient_email") or "").strip()
    aqi_data = body.get("air_quality") or {}
    aqi_val = aqi_data.get("aqi")

    if not desc or len(desc) < 10:
        return jsonify({"success": False, "message": "Description must be at least 10 characters."}), 400
    if not recipient_email or "@" not in recipient_email:
        return jsonify({"success": False, "message": "Valid recipient email is required."}), 400

    ref_id = generate_reference_id(is_test=False)
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    email_masked = mask_email(user_email) if user_email else "unprovided"
    email_hash = hash_email(user_email) if user_email else "unprovided"

    report_id = None
    try:
        report_id = create_email_report(
            location=loc_name,
            authority=auth_name,
            recipient=recipient_email,
            aqi=aqi_val if isinstance(aqi_val, (int, float)) else None,
            status="mailto_draft"
        )
    except Exception as e:
        print(f"[DB] Error creating email report for draft: {e}")

    try:
        save_complaint({
            "ref_id": ref_id,
            "user_email_masked": email_masked,
            "user_email_hash": email_hash,
            "location_name": loc_name,
            "locality": loc.get("locality"),
            "ward": loc.get("ward") or body.get("ward_code"),
            "city": loc.get("city"),
            "district": loc.get("district"),
            "state": loc.get("state"),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "aqi": aqi_val if isinstance(aqi_val, (int, float)) else None,
            "category": aqi_data.get("category"),
            "pm25": aqi_data.get("pm25") if isinstance(aqi_data.get("pm25"), (int, float)) else None,
            "pm10": aqi_data.get("pm10") if isinstance(aqi_data.get("pm10"), (int, float)) else None,
            "dominant_pollutant": aqi_data.get("dominant_pollutant"),
            "pollution_source": source,
            "complaint_description": f"[Complainant: {user_name or 'Anonymous'}]\n{desc}",
            "has_photo_evidence": bool(body.get("photo_evidence")),
            "photo_filename": None,
            "authority_name": auth_name,
            "authority_type": body.get("authority_type"),
            "authority_email": recipient_email,
            "routing_level": body.get("routing_level") or "client_selected",
            "routing_reason": "Generated mailto complaint draft for user-driven email dispatch",
            "send_status": "mailto_draft",
            "provider_response": "Mailto draft prepared & opened in client email application",
            "error_message": None,
            "client_ip": client_ip
        })
    except Exception as e:
        print(f"[DB] Error saving draft complaint: {e}")

    return jsonify({
        "success": True,
        "ref_id": ref_id,
        "report_id": report_id,
        "message": "Complaint draft recorded successfully."
    })


@app.route("/api/email/test", methods=["POST"])
def email_diagnostic_test():
    """
    Safe diagnostic endpoint to test SMTP configuration by sending
    a test verification message directly to the citizen's own mailbox.
    Never contacts any real municipal authorities.
    """
    body = request.get_json(silent=True) or {}
    user_email = (body.get("user_email") or "").strip()
    if not user_email:
        return jsonify({"success": False, "message": "Please provide your email address to receive the test message."}), 400

    result = send_test_email(to_email=user_email)
    status_code = 200 if result.get("success") else (503 if result.get("error_code") == "SMTP_NOT_CONFIGURED" else 502)
    return jsonify(result), status_code


@app.route("/api/email/reports", methods=["GET"])
def list_email_reports():
    """Retrieve recent email delivery report records from SQLite."""
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
    except ValueError:
        limit = 20
    reports = get_recent_email_reports(limit=limit)
    return jsonify({"success": True, "reports": reports, "count": len(reports)})


# Backward compatibility endpoint
@app.route("/api/send-report", methods=["POST"])
def send_email_report():
    body = request.get_json(silent=True) or {}
    # Adapt to new complaint format if user_email is present
    user_email = body.get("user_email") or "citizen.reporter@skycheck.local"
    desc = body.get("description") or "Automated air quality report dispatched by citizen via SkyCheck dashboard."
    body["user_email"] = user_email
    body["consent"] = True
    body["description"] = desc
    return submit_complaint()


if __name__ == "__main__":
    init_db()
    seed_authorities()
    print("[SkyCheck] Server running on http://127.0.0.1:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
