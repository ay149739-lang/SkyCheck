import urllib.request
import json
import sqlite3

BASE_URL = "http://127.0.0.1:5000"

def test_reports_endpoint():
    print("\n--- 1. Testing GET /api/email/reports ---")
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/email/reports")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print("Status Code:", resp.status)
            print("Response:", data)
            assert data.get("success") is True
            print("PASSED: /api/email/reports returned valid data")
    except Exception as e:
        print("FAILED /api/email/reports:", e)

def test_safe_test_email():
    print("\n--- 2. Testing POST /api/email/test (Without SMTP credentials in .env) ---")
    payload = json.dumps({"user_email": "tester@example.com"}).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE_URL}/api/email/test",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req)
        print("UNEXPECTED SUCCESS: Should not have succeeded without SMTP credentials!")
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode('utf-8'))
        print("Expected HTTP Status Code:", e.code)
        print("Response Body:", body)
        assert e.code == 503
        assert body.get("success") is False
        assert body.get("error_code") == "SMTP_NOT_CONFIGURED"
        print("PASSED: Truthfully reported SMTP_NOT_CONFIGURED without sending mock email.")

def test_complaint_submit():
    import time
    print("\n--- 3. Testing POST /api/complaints/submit ---")
    payload = json.dumps({
        "user_email": f"citizen_{int(time.time())}@example.com",
        "consent": True,
        "location": {
            "name": f"Powai Area {int(time.time()) % 1000}",
            "locality": "Powai",
            "city": "Mumbai Suburban",
            "state": "Maharashtra",
            "display_name": "Powai Lake, Mumbai"
        },
        "air_quality": {"aqi": 182, "category": "Moderate", "pm25": 85, "pm10": 130},
        "weather": {"temp": 31, "humidity": 65},
        "pollution_source": "industrial",
        "description": "Dense black smoke observed from nearby chimney during morning hours."
    }).encode('utf-8')

    req = urllib.request.Request(
        f"{BASE_URL}/api/complaints/submit",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    try:
        urllib.request.urlopen(req)
        print("UNEXPECTED SUCCESS: Should not succeed if SMTP credentials not configured!")
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode('utf-8'))
        print("HTTP Status Code:", e.code)
        print("Response Body:", body)
        assert e.code in (503, 429)
        assert body.get("success") is False
        print("PASSED: Complaint submission accurately returned error without pretending to be sent.")

def check_db_email_reports():
    print("\n--- 4. Checking database email_reports table ---")
    conn = sqlite3.connect("d:/SkyCheck/database/airguard.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, location, authority, recipient, status, aqi, error_msg, sent_at FROM email_reports ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} recent records in email_reports:")
    for r in rows:
        print(f"ID={r['id']} | Authority={r['authority']} | Recipient={r['recipient']} | Status={r['status']} | SentAt={r['sent_at']} | Error={r['error_msg']}")
    conn.close()

if __name__ == "__main__":
    test_reports_endpoint()
    test_safe_test_email()
    test_complaint_submit()
    check_db_email_reports()
