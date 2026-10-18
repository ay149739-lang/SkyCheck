"""
test_complaint_backend.py
Automated Python test suite verifying backend authority resolution,
complaint draft logging, SQLite records, and SMTP backward compatibility.
"""

import sys
import os
import json
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

from app import app
from services.authority_service import resolve_authority_for_location, get_all_verified_authorities
from database import get_recent_email_reports

def test_authority_resolution():
    print("\n--- TEST: Backend Authority Resolution ---")
    
    # 1. Mumbai Wadala -> BMC Ward F/North
    res_mumbai = resolve_authority_for_location(locality="Wadala", city="Mumbai")
    assert res_mumbai["id"] == "bmc_fn"
    assert res_mumbai["email"] == "ac.fn@mcgm.gov.in"
    assert res_mumbai["email_available"] is True
    assert res_mumbai["verification_status"] == "verified"
    print(f"[PASS] Mumbai Wadala resolved to {res_mumbai['authority_name']} ({res_mumbai['email']})")

    # 2. Delhi -> DPCC
    res_delhi = resolve_authority_for_location(city="Delhi", state="Delhi")
    assert res_delhi["id"] == "delhi_dpcc"
    assert res_delhi["email"] == "msdpcc@nic.in"
    assert res_delhi["email_available"] is True
    print(f"[PASS] Delhi resolved to {res_delhi['authority_name']} ({res_delhi['email']})")

    # 3. Bengaluru -> KSPCB
    res_bengaluru = resolve_authority_for_location(city="Bengaluru", state="Karnataka")
    assert res_bengaluru["id"] == "bbmp_kspcb"
    assert res_bengaluru["email"] == "membersecretary@kspcb.gov.in"
    assert res_bengaluru["email_available"] is True
    print(f"[PASS] Bengaluru resolved to {res_bengaluru['authority_name']} ({res_bengaluru['email']})")

    # 4. Unverified authority -> Navi Mumbai
    res_nmmc = resolve_authority_for_location(locality="Vashi", city="Navi Mumbai")
    assert res_nmmc["id"] == "nmmc_unverified"
    assert res_nmmc["email"] is None
    assert res_nmmc["email_available"] is False
    assert res_nmmc["verification_status"] == "unverified"
    print(f"[PASS] Navi Mumbai unverified authority correctly identified with email_available=False, verification_status='unverified'")


def test_api_authorities_and_draft_recording():
    print("\n--- TEST: Flask API Endpoints ---")
    client = app.test_client()

    # 1. GET /api/authorities
    resp = client.get("/api/authorities")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["count"] >= 20
    print(f"[PASS] GET /api/authorities returned {data['count']} authorities from directory.")

    # 2. POST /api/complaints/record-draft
    draft_payload = {
        "user_name": "Aarav Mehta",
        "user_email": "aarav.mehta@example.com",
        "location": {
            "name": "Matunga East",
            "ward": "F/North",
            "city": "Mumbai",
            "state": "Maharashtra"
        },
        "location_name": "Matunga East, Mumbai",
        "authority_name": "Brihanmumbai Municipal Corporation (BMC) – Ward F/North",
        "recipient_email": "ac.fn@mcgm.gov.in",
        "pollution_source": "Waste / Garbage / Plastic Burning",
        "description": "Thick toxic smoke and chemical burning odor reported from municipal dump site.",
        "air_quality": {
            "aqi": 188,
            "category": "Moderate",
            "pm25": 92,
            "pm10": 140
        }
    }
    resp = client.post("/api/complaints/record-draft", json=draft_payload)
    assert resp.status_code == 200
    res_data = resp.get_json()
    assert res_data["success"] is True
    assert "ref_id" in res_data
    assert res_data["ref_id"].startswith("SKY-")
    print(f"[PASS] POST /api/complaints/record-draft created audit record with Ref ID: {res_data['ref_id']}")

    # 3. Verify SQLite persistence in email_reports and complaints
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "airguard.db")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, location, authority, recipient, status FROM email_reports WHERE id = ?", (res_data["report_id"],))
    row = cur.fetchone()
    assert row is not None
    assert row[4] == "mailto_draft"
    print(f"[PASS] SQLite email_reports table verified for report ID {row[0]} with status '{row[4]}'.")
    conn.close()


def test_smtp_isolation():
    print("\n--- TEST: SMTP Features Isolation (Not Broken) ---")
    client = app.test_client()

    # Diagnostic test endpoint should report truthfully if SMTP is not configured
    resp = client.post("/api/email/test", json={"user_email": "tester@example.com"})
    # Expect 503 or 200 depending on .env SMTP configuration
    assert resp.status_code in [200, 502, 503]
    print(f"[PASS] POST /api/email/test responded with status {resp.status_code} without breaking.")

    # Legacy submit endpoint
    resp = client.post("/api/complaints/submit", json={})
    assert resp.status_code == 400
    print("[PASS] POST /api/complaints/submit payload validation intact.")


if __name__ == "__main__":
    test_authority_resolution()
    test_api_authorities_and_draft_recording()
    test_smtp_isolation()
    print("\n======================================================================")
    print(">>> ALL BACKEND TESTS PASSED SUCCESSFULLY! <<<")
    print("======================================================================\n")
