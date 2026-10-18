"""
email_service.py – Location-Aware Citizen Environmental Complaint Dispatch Service
Implements:
1. Strict server-side input validation & header injection sanitization.
2. Authority resolution verification against trusted directory (never trusts client-supplied recipient).
3. Anti-duplicate submission protection & rate limiting.
4. Professional multipart (Plain text + HTML) complaint templates with NAQI table & evidence attachment.
5. Live SMTP dispatch when configured; transparent Development Test Mode (Mock) when unconfigured.
6. Persistent complaint audit logging in SQLite without leaking sensitive secrets.
"""

import os
import re
import time
import base64
import random
import ssl
import socket
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.application import MIMEApplication
from typing import Dict, Any, Optional, Tuple

from config import (
    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM,
    smtp_configured, validate_smtp_credentials
)
from database import (
    save_complaint, check_recent_complaint, hash_email, mask_email,
    create_email_report, update_email_report
)
from services.authority_service import resolve_authority_for_location

# In-memory rate limiting: { "hash_or_ip": [timestamps] }
_RATE_LIMIT_STORE: Dict[str, list] = {}
RATE_LIMIT_MAX_PER_WINDOW = 3
RATE_LIMIT_WINDOW_SECONDS = 600  # 10 minutes

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def _sanitize_header(text: Optional[str]) -> str:
    """Strip carriage return and newline characters to prevent email header injection."""
    if not text:
        return ""
    return re.sub(r"[\r\n]+", " ", str(text)).strip()


def _is_rate_limited(identifier: str) -> bool:
    now = time.time()
    history = _RATE_LIMIT_STORE.setdefault(identifier, [])
    # purge old
    _RATE_LIMIT_STORE[identifier] = [t for t in history if now - t < RATE_LIMIT_WINDOW_SECONDS]
    if len(_RATE_LIMIT_STORE[identifier]) >= RATE_LIMIT_MAX_PER_WINDOW:
        return True
    _RATE_LIMIT_STORE[identifier].append(now)
    return False


def generate_reference_id(is_test: bool = False) -> str:
    year = datetime.now().year
    random_num = random.randint(10000, 99999)
    prefix = "SKY-TEST" if is_test else "SKY"
    return f"{prefix}-{year}-{random_num}"


def validate_complaint_payload(body: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate all required fields on backend before processing."""
    email = (body.get("user_email") or "").strip()
    if not email or not EMAIL_REGEX.match(email):
        return False, "Please provide a valid citizen email address for official correspondence."

    consent = body.get("consent")
    if not consent:
        return False, "You must check the consent box to authorize sending this pollution report."

    description = (body.get("description") or "").strip()
    if len(description) < 10:
        return False, "Complaint description is too short (minimum 10 characters required)."
    if len(description) > 3000:
        return False, "Complaint description exceeds the maximum length (3,000 characters)."

    location = body.get("location") or {}
    if not location.get("name") and not location.get("display_name"):
        return False, "Valid location information is required for jurisdiction routing."

    return True, None


def build_email_bodies(
    ref_id: str,
    user_email: str,
    location: Dict[str, Any],
    aqi_data: Dict[str, Any],
    weather_data: Dict[str, Any],
    authority: Dict[str, Any],
    pollution_source: str,
    complaint_description: str,
    is_test: bool
) -> Tuple[str, str]:
    """Generates both Plain Text and Responsive HTML email templates."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    loc_name = location.get("name") or location.get("locality") or "Reported Location"
    display_name = location.get("display_name") or loc_name
    city = location.get("city") or "N/A"
    district = location.get("district") or "N/A"
    state = location.get("state") or "N/A"
    lat = location.get("latitude", "N/A")
    lon = location.get("longitude", "N/A")

    aqi_val = aqi_data.get("aqi", "N/A")
    category = aqi_data.get("category", "N/A")
    pm25 = aqi_data.get("pm25", "N/A")
    pm10 = aqi_data.get("pm10", "N/A")
    no2 = aqi_data.get("no2", "N/A")
    so2 = aqi_data.get("so2", "N/A")
    co = aqi_data.get("co", "N/A")
    o3 = aqi_data.get("o3", "N/A")

    temp = weather_data.get("temperature", "N/A")
    humidity = weather_data.get("humidity", "N/A")
    wind = weather_data.get("wind", "N/A")

    auth_name = authority.get("authority_name", "Environmental Regulatory Authority")
    jurisdiction = authority.get("jurisdiction_scope", "Local Jurisdiction")
    portal_url = authority.get("portal_url") or "https://sameer.cpcb.gov.in"
    source_url = authority.get("official_source_url") or authority.get("website") or "https://cpcb.nic.in"

    test_banner = "\n*** DEVELOPMENT TEST TRANSMISSION (MOCK MODE) ***\n" if is_test else ""

    # Plain Text
    plain_text = f"""======================================================================
SKYCHECK AIRGUARD AI - OFFICIAL CITIZEN AIR POLLUTION COMPLAINT
Reference ID: {ref_id}
Timestamp   : {now_utc}{test_banner}
======================================================================

TO: {auth_name}
JURISDICTION: {jurisdiction}

CITIZEN COMPLAINANT:
----------------------------------------------------------------------
Complainant Email : {user_email} (Reply-To enabled)
Official Notice   : This complaint was filed by a citizen via SkyCheck.
                    Replies to this email will be routed directly to the citizen.

INCIDENT LOCATION:
----------------------------------------------------------------------
Locality / Ward   : {loc_name}
Full Address      : {display_name}
City / District   : {city}, {district}
State / Country   : {state}, India
GPS Coordinates   : {lat}, {lon}

INCIDENT SUMMARY & POLLUTION SOURCE:
----------------------------------------------------------------------
Reported Source   : {pollution_source or 'Unspecified Atmospheric Emission'}
Citizen Statement :
{complaint_description}

ATMOSPHERIC OBSERVATIONS AT TIME OF COMPLAINT:
----------------------------------------------------------------------
Indian NAQI (CPCB): {aqi_val} - {category}
PM2.5 (Fine Dust) : {pm25} µg/m³
PM10 (Coarse Dust): {pm10} µg/m³
Nitrogen Dioxide  : {no2} µg/m³
Sulfur Dioxide    : {so2} µg/m³
Carbon Monoxide   : {co} mg/m³
Ozone (O3)        : {o3} µg/m³
Temperature       : {temp} °C | Humidity: {humidity}% | Wind: {wind} m/s

AUTHORITY ROUTING & VERIFICATION:
----------------------------------------------------------------------
Authority Contact : {authority.get('email', 'Official Portal')}
Verification Source: {source_url}
Online Portal     : {portal_url}

DISCLAIMER:
This email alert transmits citizen-submitted environmental observations.
Provider acceptance acknowledges receipt into the official gateway.
Inspection and administrative actions are governed by statutory guidelines.
======================================================================
"""

    # Responsive HTML Template
    cat_colors = {
        "Good": "#00b050", "Satisfactory": "#8bc34a",
        "Moderate": "#fbc02d", "Poor": "#ff7e00",
        "Very Poor": "#e53935", "Severe": "#880e4f"
    }
    badge_color = cat_colors.get(category, "#2196f3")

    test_html_badge = (
        '<div style="background:#fff3cd; color:#856404; padding:8px 12px; border-radius:6px; margin-bottom:15px; font-weight:bold; text-align:center;">'
        '⚠ NOTICE: This is a verified development test transmission (Mock Mode).'
        '</div>'
    ) if is_test else ""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #2d3748; }}
  .container {{ max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.08); border: 1px solid #e2e8f0; }}
  .header {{ background: linear-gradient(135deg, #1e3a8a, #3b82f6); color: #ffffff; padding: 24px; text-align: center; }}
  .header h1 {{ margin: 0; font-size: 20px; letter-spacing: -0.3px; }}
  .header p {{ margin: 6px 0 0; opacity: 0.9; font-size: 13px; }}
  .ref-pill {{ display: inline-block; background: rgba(255,255,255,0.22); padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-top: 10px; }}
  .content {{ padding: 24px; }}
  .section {{ margin-bottom: 22px; }}
  .section-title {{ font-size: 13px; font-weight: 700; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px; border-bottom: 2px solid #f1f5f9; padding-bottom: 6px; margin-bottom: 12px; }}
  .data-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }}
  .data-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; }}
  .data-label {{ font-size: 11px; color: #64748b; font-weight: 600; text-transform: uppercase; }}
  .data-value {{ font-size: 14px; font-weight: 600; color: #1e293b; margin-top: 2px; }}
  .aqi-banner {{ background: #f8fafc; border-left: 5px solid {badge_color}; border-radius: 6px; padding: 14px; margin: 15px 0; display: flex; align-items: center; justify-content: space-between; }}
  .aqi-num {{ font-size: 24px; font-weight: 800; color: {badge_color}; }}
  .aqi-cat {{ font-size: 14px; font-weight: 700; color: #1e293b; }}
  .statement-box {{ background: #f1f5f9; border-left: 4px solid #3b82f6; padding: 14px 16px; border-radius: 6px; font-size: 14px; line-height: 1.6; color: #1e293b; white-space: pre-wrap; }}
  .footer {{ background: #f8fafc; padding: 16px 24px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; line-height: 1.5; }}
  .source-link {{ color: #2563eb; text-decoration: none; font-weight: 600; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Air Quality Incident Report</h1>
    <p>SkyCheck Citizen Environmental Alert Platform</p>
    <div class="ref-pill">Ref: {ref_id}</div>
  </div>
  <div class="content">
    {test_html_badge}

    <div class="section">
      <div class="section-title">Designated Environmental Authority</div>
      <div class="data-card">
        <div class="data-label">Recipient Authority</div>
        <div class="data-value">{auth_name}</div>
        <div style="font-size:12px; color:#64748b; margin-top:4px;">Jurisdiction: {jurisdiction}</div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Complainant & Reply-To Details</div>
      <div class="data-card">
        <div class="data-label">Citizen Contact</div>
        <div class="data-value">{user_email}</div>
        <div style="font-size:11px; color:#64748b; margin-top:4px;">Direct replies to this email dispatch will be received by the complainant.</div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Incident Location</div>
      <div class="data-card">
        <div class="data-value">{loc_name}</div>
        <div style="font-size:12px; color:#475569; margin:4px 0;">{display_name}</div>
        <div style="font-size:11px; color:#64748b;">Coordinates: {lat}, {lon} • District: {district}, {state}</div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Atmospheric Readings (Time of Report)</div>
      <div class="aqi-banner">
        <div>
          <div style="font-size:11px; text-transform:uppercase; color:#64748b; font-weight:700;">Recorded Indian NAQI</div>
          <div class="aqi-cat">{category} Air Quality</div>
        </div>
        <div class="aqi-num">{aqi_val}</div>
      </div>
      <table style="width:100%; border-collapse:collapse; font-size:12px; margin-top:8px;">
        <tr style="background:#f8fafc; border-bottom:1px solid #e2e8f0;">
          <th style="padding:6px; text-align:left;">PM2.5</th>
          <th style="padding:6px; text-align:left;">PM10</th>
          <th style="padding:6px; text-align:left;">NO₂</th>
          <th style="padding:6px; text-align:left;">SO₂</th>
          <th style="padding:6px; text-align:left;">CO</th>
          <th style="padding:6px; text-align:left;">O₃</th>
        </tr>
        <tr>
          <td style="padding:6px;">{pm25} µg/m³</td>
          <td style="padding:6px;">{pm10} µg/m³</td>
          <td style="padding:6px;">{no2} µg/m³</td>
          <td style="padding:6px;">{so2} µg/m³</td>
          <td style="padding:6px;">{co} mg/m³</td>
          <td style="padding:6px;">{o3} µg/m³</td>
        </tr>
      </table>
    </div>

    <div class="section">
      <div class="section-title">Citizen Incident Description</div>
      <div style="margin-bottom:8px;">
        <span style="font-size:12px; font-weight:700; color:#475569;">Reported Source:</span>
        <span style="font-size:12px; background:#e0f2fe; color:#0369a1; padding:2px 8px; border-radius:12px; font-weight:600;">{pollution_source or 'General Emission'}</span>
      </div>
      <div class="statement-box">{complaint_description}</div>
    </div>
  </div>
  <div class="footer">
    <p>Official Verification Source: <a href="{source_url}" class="source-link" target="_blank">{source_url}</a></p>
    <p>Official Grievance Portal: <a href="{portal_url}" class="source-link" target="_blank">{portal_url}</a></p>
    <p style="margin-top:8px; font-size:11px;">Transmitted via SkyCheck Citizen Environmental Monitoring Platform • Timestamp: {now_utc}</p>
  </div>
</div>
</body>
</html>
"""
    return plain_text, html


def send_complaint(
    user_email: str,
    location: Dict[str, Any],
    aqi_data: Dict[str, Any],
    weather_data: Dict[str, Any],
    complaint_description: str,
    pollution_source: str = "General",
    photo_data_base64: Optional[str] = None,
    client_ip: str = "127.0.0.1"
) -> Dict[str, Any]:
    """
    Main entry point for processing and transmitting citizen complaints.
    Resolves recipient authority strictly from verified backend directory.
    """
    user_email = _sanitize_header(user_email)
    user_hash = hash_email(user_email)
    user_masked = mask_email(user_email)
    loc_name = _sanitize_header(location.get("name") or location.get("locality") or "Location")

    # Anti-duplicate check (within 5 minutes)
    if check_recent_complaint(user_hash, loc_name, minutes=5):
        return {
            "success": False,
            "error_code": "DUPLICATE_SUBMISSION",
            "message": f"A complaint for '{loc_name}' was already submitted by your email recently. Please wait a few minutes before submitting another report."
        }

    # Rate limiting
    if _is_rate_limited(user_hash) or _is_rate_limited(client_ip):
        return {
            "success": False,
            "error_code": "RATE_LIMIT_EXCEEDED",
            "message": "Submission rate limit reached (max 3 complaints per 10 minutes). Please try again shortly."
        }

    # Resolve responsible authority from verified backend directory
    authority = resolve_authority_for_location(
        locality=location.get("locality") or location.get("name") or "",
        city=location.get("city") or "",
        district=location.get("district") or "",
        state=location.get("state") or "",
        display_name=location.get("display_name") or ""
    )

    recipient_email = _sanitize_header(authority.get("email"))
    auth_name = authority.get("authority_name", "Environmental Authority")
    aqi_val = aqi_data.get("aqi")
    ref_id = generate_reference_id(is_test=False)

    # 1. Recipient check: strictly use authority's configured email without inventing addresses
    if not recipient_email or "@" not in recipient_email:
        err_msg = (
            f"The identified authority '{auth_name}' does not have a verified email address registered in our directory. "
            f"Please file your grievance directly through their official portal."
        )
        report_id = create_email_report(
            location=loc_name,
            authority=auth_name,
            recipient="N/A (No verified email)",
            aqi=aqi_val,
            status="failed"
        )
        update_email_report(report_id, status="failed", error_msg=err_msg)

        save_complaint({
            "ref_id": ref_id,
            "user_email_masked": user_masked,
            "user_email_hash": user_hash,
            "location_name": loc_name,
            "locality": location.get("locality"),
            "ward": authority.get("ward_code"),
            "city": location.get("city"),
            "district": location.get("district"),
            "state": location.get("state"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "aqi": aqi_val,
            "category": aqi_data.get("category"),
            "pm25": aqi_data.get("pm25"),
            "pm10": aqi_data.get("pm10"),
            "dominant_pollutant": aqi_data.get("dominant_pollutant"),
            "pollution_source": pollution_source,
            "complaint_description": complaint_description,
            "has_photo_evidence": False,
            "photo_filename": None,
            "authority_name": auth_name,
            "authority_type": authority.get("authority_type"),
            "authority_email": None,
            "routing_level": authority.get("match_level"),
            "routing_reason": authority.get("routing_explanation"),
            "send_status": "failed",
            "provider_response": None,
            "error_message": err_msg,
            "client_ip": client_ip
        })

        return {
            "success": False,
            "error_code": "AUTHORITY_EMAIL_NOT_AVAILABLE",
            "ref_id": ref_id,
            "report_id": report_id,
            "authority_name": auth_name,
            "portal_url": authority.get("portal_url"),
            "message": err_msg,
            "actionable_portal": authority.get("portal_url")
        }

    # 2. Validate SMTP credentials before attempting transmission
    is_smtp_valid, smtp_val_msg = validate_smtp_credentials()
    if not is_smtp_valid:
        err_msg = f"Email dispatch cannot proceed: {smtp_val_msg}. Please configure real credentials in .env to send live reports."
        report_id = create_email_report(
            location=loc_name,
            authority=auth_name,
            recipient=recipient_email,
            aqi=aqi_val,
            status="failed"
        )
        update_email_report(report_id, status="failed", error_msg=err_msg)

        save_complaint({
            "ref_id": ref_id,
            "user_email_masked": user_masked,
            "user_email_hash": user_hash,
            "location_name": loc_name,
            "locality": location.get("locality"),
            "ward": authority.get("ward_code"),
            "city": location.get("city"),
            "district": location.get("district"),
            "state": location.get("state"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "aqi": aqi_val,
            "category": aqi_data.get("category"),
            "pm25": aqi_data.get("pm25"),
            "pm10": aqi_data.get("pm10"),
            "dominant_pollutant": aqi_data.get("dominant_pollutant"),
            "pollution_source": pollution_source,
            "complaint_description": complaint_description,
            "has_photo_evidence": bool(photo_data_base64),
            "photo_filename": None,
            "authority_name": auth_name,
            "authority_type": authority.get("authority_type"),
            "authority_email": recipient_email,
            "routing_level": authority.get("match_level"),
            "routing_reason": authority.get("routing_explanation"),
            "send_status": "failed",
            "provider_response": None,
            "error_message": err_msg,
            "client_ip": client_ip
        })

        return {
            "success": False,
            "error_code": "SMTP_NOT_CONFIGURED",
            "ref_id": ref_id,
            "report_id": report_id,
            "authority_name": auth_name,
            "authority_email": recipient_email,
            "portal_url": authority.get("portal_url"),
            "message": err_msg,
            "actionable_portal": authority.get("portal_url")
        }

    # 3. Build email contents
    plain_text, html_body = build_email_bodies(
        ref_id=ref_id,
        user_email=user_email,
        location=location,
        aqi_data=aqi_data,
        weather_data=weather_data,
        authority=authority,
        pollution_source=pollution_source,
        complaint_description=complaint_description,
        is_test=False
    )

    subject = _sanitize_header(
        f"Air Pollution Complaint — {loc_name}, {location.get('city', '')} "
        f"(AQI: {aqi_data.get('aqi', 'N/A')} - {aqi_data.get('category', 'NAQI')}) [{ref_id}]"
    )

    # Construct MIME message
    sender = SMTP_FROM or SMTP_USERNAME
    msg = MIMEMultipart("mixed")
    msg["From"] = _sanitize_header(sender)
    msg["To"] = recipient_email
    msg["Reply-To"] = user_email
    msg["Subject"] = subject

    # Add secondary escalation if present
    sec_email = _sanitize_header(authority.get("secondary_email"))
    if sec_email and "@" in sec_email:
        msg["Cc"] = sec_email

    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(plain_text, "plain", "utf-8"))
    alt_part.attach(MIMEText(html_body, "html", "utf-8"))
    msg.attach(alt_part)

    # Process and attach photo evidence if provided
    has_photo = False
    photo_filename = None
    if photo_data_base64:
        try:
            if "," in photo_data_base64:
                header_part, base64_data = photo_data_base64.split(",", 1)
            else:
                base64_data = photo_data_base64

            binary_data = base64.b64decode(base64_data)
            if len(binary_data) <= 5 * 1024 * 1024:
                ext = "jpg"
                if "png" in (photo_data_base64[:30].lower()):
                    ext = "png"
                elif "webp" in (photo_data_base64[:30].lower()):
                    ext = "webp"

                photo_filename = f"evidence_{ref_id}.{ext}"
                img_part = MIMEImage(binary_data, name=photo_filename)
                img_part.add_header("Content-Disposition", "attachment", filename=photo_filename)
                msg.attach(img_part)
                has_photo = True
        except Exception as e:
            print(f"[EmailService] Photo attachment parsing error: {e}")

    # 4. Create pending record in email_reports table
    report_id = create_email_report(
        location=loc_name,
        authority=auth_name,
        recipient=recipient_email,
        aqi=aqi_val,
        status="pending"
    )

    # 5. Dispatch via SMTP
    to_addrs = [recipient_email]
    cc_addrs = [sec_email] if (sec_email and "@" in sec_email) else None

    send_success, provider_response, error_msg = _send_smtp_email(
        from_addr=sender,
        to_addrs=to_addrs,
        msg=msg,
        cc_addrs=cc_addrs
    )

    if send_success:
        update_email_report(report_id, status="sent", error_msg=None)
        save_complaint({
            "ref_id": ref_id,
            "user_email_masked": user_masked,
            "user_email_hash": user_hash,
            "location_name": loc_name,
            "locality": location.get("locality"),
            "ward": authority.get("ward_code"),
            "city": location.get("city"),
            "district": location.get("district"),
            "state": location.get("state"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "aqi": aqi_val,
            "category": aqi_data.get("category"),
            "pm25": aqi_data.get("pm25"),
            "pm10": aqi_data.get("pm10"),
            "dominant_pollutant": aqi_data.get("dominant_pollutant"),
            "pollution_source": pollution_source,
            "complaint_description": complaint_description,
            "has_photo_evidence": has_photo,
            "photo_filename": photo_filename,
            "authority_name": auth_name,
            "authority_type": authority.get("authority_type"),
            "authority_email": recipient_email,
            "routing_level": authority.get("match_level"),
            "routing_reason": authority.get("routing_explanation"),
            "send_status": "sent",
            "provider_response": provider_response,
            "error_message": None,
            "client_ip": client_ip
        })

        return {
            "success": True,
            "ref_id": ref_id,
            "report_id": report_id,
            "is_test": False,
            "authority_name": auth_name,
            "authority_email": recipient_email,
            "routing_explanation": authority.get("routing_explanation"),
            "portal_url": authority.get("portal_url"),
            "message": f"Email accepted by SMTP server for delivery to {auth_name} ({recipient_email}).",
            "disclaimer": "SMTP acceptance confirms transmission to the mail provider. Final administrative review or on-site inspection depends on government timelines."
        }
    else:
        update_email_report(report_id, status="failed", error_msg=error_msg)
        save_complaint({
            "ref_id": ref_id,
            "user_email_masked": user_masked,
            "user_email_hash": user_hash,
            "location_name": loc_name,
            "locality": location.get("locality"),
            "ward": authority.get("ward_code"),
            "city": location.get("city"),
            "district": location.get("district"),
            "state": location.get("state"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "aqi": aqi_val,
            "category": aqi_data.get("category"),
            "pm25": aqi_data.get("pm25"),
            "pm10": aqi_data.get("pm10"),
            "dominant_pollutant": aqi_data.get("dominant_pollutant"),
            "pollution_source": pollution_source,
            "complaint_description": complaint_description,
            "has_photo_evidence": has_photo,
            "photo_filename": photo_filename,
            "authority_name": auth_name,
            "authority_type": authority.get("authority_type"),
            "authority_email": recipient_email,
            "routing_level": authority.get("match_level"),
            "routing_reason": authority.get("routing_explanation"),
            "send_status": "failed",
            "provider_response": None,
            "error_message": error_msg,
            "client_ip": client_ip
        })

        return {
            "success": False,
            "error_code": "SMTP_DELIVERY_FAILED",
            "ref_id": ref_id,
            "report_id": report_id,
            "authority_name": auth_name,
            "authority_email": recipient_email,
            "portal_url": authority.get("portal_url"),
            "message": f"Email transmission failed: {error_msg}",
            "actionable_portal": authority.get("portal_url")
        }


def _send_smtp_email(
    from_addr: str,
    to_addrs: list,
    msg: MIMEMultipart,
    cc_addrs: Optional[list] = None
) -> Tuple[bool, str, Optional[str]]:
    """
    Connects to configured SMTP server, handles Port 465 (SSL) and Port 587 (STARTTLS),
    authenticates, and transmits message.
    Returns (success: bool, provider_response: str, error_msg: Optional[str]).
    """
    is_valid, validation_msg = validate_smtp_credentials()
    if not is_valid:
        return False, "", validation_msg

    all_recipients = [a.strip() for a in to_addrs if a and "@" in a]
    if cc_addrs:
        for c in cc_addrs:
            c_clean = c.strip() if c else ""
            if c_clean and "@" in c_clean and c_clean not in all_recipients:
                all_recipients.append(c_clean)

    if not all_recipients:
        return False, "", "No valid recipient email addresses found."

    sender = from_addr or SMTP_FROM or SMTP_USERNAME
    if not sender or "@" not in sender:
        return False, "", "Invalid sender address. Please set SMTP_FROM_EMAIL or SMTP_USERNAME in .env."

    try:
        # Port 465 uses SSL directly (SMTPS)
        if SMTP_PORT == 465:
            ssl_ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl_ctx) as server:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(sender, all_recipients, msg.as_string())
        # Port 587 / 25 / other uses standard SMTP with STARTTLS
        else:
            ssl_ctx = ssl.create_default_context()
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.ehlo()
                if server.has_extn("STARTTLS"):
                    server.starttls(context=ssl_ctx)
                    server.ehlo()
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(sender, all_recipients, msg.as_string())

        provider_resp = f"SMTP 250 Accepted by {SMTP_HOST}"
        return True, provider_resp, None

    except smtplib.SMTPAuthenticationError:
        safe_msg = f"SMTP authentication failed on {SMTP_HOST}. Verify your SMTP_USERNAME and SMTP_PASSWORD/App Password in .env."
        return False, "", safe_msg
    except smtplib.SMTPRecipientsRefused:
        safe_msg = f"SMTP server rejected the recipient email address."
        return False, "", safe_msg
    except smtplib.SMTPSenderRefused:
        safe_msg = f"SMTP server rejected the sender address '{sender}'. Check SMTP_FROM_EMAIL in .env."
        return False, "", safe_msg
    except (smtplib.SMTPConnectError, ConnectionRefusedError):
        safe_msg = f"Failed to connect to SMTP server at {SMTP_HOST}:{SMTP_PORT}. Check host, port, and network connection."
        return False, "", safe_msg
    except (socket.timeout, TimeoutError):
        safe_msg = f"Connection to SMTP server at {SMTP_HOST}:{SMTP_PORT} timed out (20-second timeout exceeded)."
        return False, "", safe_msg
    except ssl.SSLError:
        safe_msg = f"SSL/TLS handshake error with {SMTP_HOST}:{SMTP_PORT}. Ensure port 465 is used for SSL or port 587 for STARTTLS."
        return False, "", safe_msg
    except smtplib.SMTPException as e:
        safe_msg = f"SMTP transmission error: {type(e).__name__} - {str(e)}"
        return False, "", safe_msg
    except Exception as e:
        safe_msg = f"Email gateway error: {str(e)}"
        return False, "", safe_msg


def send_test_email(to_email: str) -> Dict[str, Any]:
    """
    Sends a safe, direct test email to the user's provided address.
    NEVER contacts any real municipal authorities or government mailboxes.
    Logs record in email_reports table.
    """
    to_email = _sanitize_header(to_email)
    if not to_email or "@" not in to_email:
        return {
            "success": False,
            "error_code": "INVALID_EMAIL",
            "message": "Please enter a valid destination email address to receive the test message."
        }

    is_valid, validation_msg = validate_smtp_credentials()
    if not is_valid:
        return {
            "success": False,
            "error_code": "SMTP_NOT_CONFIGURED",
            "message": f"Cannot send test email: {validation_msg}."
        }

    ref_id = f"SKY-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    sender = SMTP_FROM or SMTP_USERNAME
    msg = MIMEMultipart("alternative")
    msg["From"] = _sanitize_header(sender)
    msg["To"] = to_email
    msg["Subject"] = f"[SkyCheck Test] SMTP Delivery Verification [{ref_id}]"

    plain_text = f"""SkyCheck / AirGuard AI — SMTP Diagnostic Test
======================================================
Reference ID: {ref_id}
Timestamp: {timestamp_str}
SMTP Host: {SMTP_HOST}:{SMTP_PORT}
Authenticated User: {SMTP_USERNAME}
Test Recipient: {to_email}

This is an automated test message sent by SkyCheck to verify your email server configuration.
If you are reading this, your SMTP settings in .env are working correctly!

Note: No municipal or government authorities were contacted for this test.
"""

    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 24px; margin: 0;">
    <div style="max-width: 600px; margin: 0 auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.4);">
        <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px 24px; color: #ffffff;">
            <h2 style="margin: 0; font-size: 20px;">SkyCheck — SMTP Test Verification</h2>
            <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Safe Self-Diagnostic Email (No Authorities Contacted)</p>
        </div>
        <div style="padding: 24px;">
            <p style="font-size: 15px; line-height: 1.5; color: #cbd5e1; margin-top: 0;">
                Congratulations! If you received this email, your <strong>SkyCheck SMTP configuration</strong> in <code>.env</code> is verified and communicating properly with <strong>{SMTP_HOST}</strong>.
            </p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; background: #0f172a; border-radius: 8px; overflow: hidden;">
                <tr><td style="padding: 10px 14px; border-bottom: 1px solid #334155; color: #94a3b8;">Reference ID:</td><td style="padding: 10px 14px; border-bottom: 1px solid #334155; font-weight: 600; color: #38bdf8;">{ref_id}</td></tr>
                <tr><td style="padding: 10px 14px; border-bottom: 1px solid #334155; color: #94a3b8;">Timestamp:</td><td style="padding: 10px 14px; border-bottom: 1px solid #334155; color: #e2e8f0;">{timestamp_str}</td></tr>
                <tr><td style="padding: 10px 14px; border-bottom: 1px solid #334155; color: #94a3b8;">SMTP Host:</td><td style="padding: 10px 14px; border-bottom: 1px solid #334155; color: #e2e8f0;">{SMTP_HOST}:{SMTP_PORT}</td></tr>
                <tr><td style="padding: 10px 14px; border-bottom: 1px solid #334155; color: #94a3b8;">Sender (From):</td><td style="padding: 10px 14px; border-bottom: 1px solid #334155; color: #e2e8f0;">{sender}</td></tr>
                <tr><td style="padding: 10px 14px; color: #94a3b8;">Recipient (To):</td><td style="padding: 10px 14px; color: #e2e8f0;">{to_email}</td></tr>
            </table>
            <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 12px 16px; font-size: 12px; color: #6ee7b7;">
                <strong>Safe Test Notice:</strong> This test email was delivered directly to your personal mailbox. No municipal corporations, state pollution control boards, or central portals were contacted.
            </div>
        </div>
    </div>
</body>
</html>
"""
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    report_id = create_email_report(
        location="Diagnostic Self-Test",
        authority="Citizen Test Dispatcher",
        recipient=to_email,
        aqi=0.0,
        status="pending"
    )

    success, provider_resp, err_msg = _send_smtp_email(
        from_addr=sender,
        to_addrs=[to_email],
        msg=msg
    )

    if success:
        update_email_report(report_id, status="sent", error_msg=None)
        return {
            "success": True,
            "ref_id": ref_id,
            "report_id": report_id,
            "recipient": to_email,
            "smtp_host": SMTP_HOST,
            "message": f"Test email successfully accepted by {SMTP_HOST} for delivery to {to_email}. Please check your inbox (and spam/junk folder).",
            "disclaimer": "SMTP acceptance confirms transmission to your mail server. Actual arrival in your inbox may take 1-2 minutes."
        }
    else:
        update_email_report(report_id, status="failed", error_msg=err_msg)
        return {
            "success": False,
            "error_code": "SMTP_TEST_FAILED",
            "ref_id": ref_id,
            "report_id": report_id,
            "recipient": to_email,
            "message": f"SMTP test failed: {err_msg}"
        }
