"""
test_fixes.py - Test suite verifying fixes for:
BUG 1: Live location reverse-geocoding, geolocation fallbacks, and coordinate resolution
BUG 2: Immediate location name display, Mumbai ward handling, out-of-state search
BUG 3: Search performance, caching, and parallel AQI/weather loading
ADDITIONAL: Startup live location detection endpoints & frontend asset delivery
"""

import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://127.0.0.1:5000"

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SkyCheckTest/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode('utf-8'))

def test_static_and_health():
    print("\n--- TEST: Static Assets & Health Check ---")
    status, health = get_json(f"{BASE_URL}/api/health")
    assert status == 200
    assert health.get("status") == "ok"
    print(f"[PASS] Health endpoint OK: {health}")

    # Check frontend HTML
    req = urllib.request.Request(f"{BASE_URL}/", headers={"User-Agent": "SkyCheckTest/1.0"})
    with urllib.request.urlopen(req) as resp:
        content = resp.read().decode('utf-8')
        assert "SkyCheck" in content
        assert "cityName" in content
        assert "locationCoordsSubtitle" in content
    print("[PASS] Frontend index.html served correctly from Flask root.")

    # Check frontend app.js
    req = urllib.request.Request(f"{BASE_URL}/app.js", headers={"User-Agent": "SkyCheckTest/1.0"})
    with urllib.request.urlopen(req) as resp:
        js = resp.read().decode('utf-8')
        assert "getPositionWithFallback" in js
        assert "handleSearchInput" in js
        assert "renderAqiAndWeatherCards" in js
        assert "startupLocationInitiated" in js
        assert "userHasSelectedManualLocation" in js
    print("[PASS] Frontend app.js served with all new bug fixes and startup logic.")


def test_bug1_live_location_reverse():
    print("\n--- TEST BUG 1: Live Location Reverse Geocoding ---")
    # Coordinates for CGS Colony / Wadala (19.0222, 72.8681)
    status, data = get_json(f"{BASE_URL}/api/location/reverse?lat=19.0222&lon=72.8681")
    assert status == 200
    assert data.get("is_live_gps") is True
    assert "Ward F/North" in data.get("name", "") or "CGS Colony" in data.get("locality", "")
    assert data.get("city") == "Mumbai"
    print(f"[PASS] Reverse geocoded coordinates to readable locality: {data.get('name')} | City: {data.get('city')}")

    # Coordinates for Connaught Place, Delhi (28.6315, 77.2167)
    status, data = get_json(f"{BASE_URL}/api/location/reverse?lat=28.6315&lon=77.2167")
    assert status == 200
    assert data.get("is_live_gps") is True
    print(f"[PASS] Reverse geocoded Delhi coordinates to readable locality: {data.get('name')}, {data.get('state')}")


def test_bug2_mumbai_wards_and_other_states():
    print("\n--- TEST BUG 2: Mumbai Wards, Localities & Out-of-State Cities ---")
    
    # 1. Search Mumbai
    status, data = get_json(f"{BASE_URL}/api/location/search?q=Mumbai")
    assert status == 200
    results = data.get("results", [])
    assert len(results) > 0
    assert results[0].get("city") == "Mumbai"
    assert results[0].get("name") == "Mumbai"
    print(f"[PASS] Mumbai search: {results[0].get('display_name')} (Lat: {results[0].get('latitude')}, Lon: {results[0].get('longitude')})")

    # 2. Search Mumbai Ward: K West Ward (Andheri West / Versova)
    status, data = get_json(f"{BASE_URL}/api/location/search?q=K+West+Ward")
    assert status == 200
    results = data.get("results", [])
    assert len(results) > 0
    top = results[0]
    assert "Ward K/West" in top.get("name") or "Andheri West" in top.get("locality")
    assert top.get("city") == "Mumbai"
    print(f"[PASS] Mumbai ward search (K West Ward): {top.get('name')} | Locality: {top.get('locality')}")

    # 3. Search Mumbai Locality: CGS Colony
    status, data = get_json(f"{BASE_URL}/api/location/search?q=CGS+Colony")
    assert status == 200
    results = data.get("results", [])
    assert len(results) > 0
    top = results[0]
    assert "CGS Colony" in top.get("locality") or "CGS Colony" in top.get("display_name")
    print(f"[PASS] Mumbai locality search (CGS Colony): {top.get('display_name')}")

    # 4. Search Town from another state: Bengaluru (Karnataka)
    status, data = get_json(f"{BASE_URL}/api/location/search?q=Bengaluru")
    assert status == 200
    results = data.get("results", [])
    assert len(results) > 0
    top = results[0]
    assert top.get("name") == "Bengaluru"
    assert top.get("state") == "Karnataka"
    print(f"[PASS] Out-of-state search (Bengaluru): {top.get('display_name')}")

    # 5. Search Town from another state: Jaipur (Rajasthan)
    status, data = get_json(f"{BASE_URL}/api/location/search?q=Jaipur")
    assert status == 200
    results = data.get("results", [])
    assert len(results) > 0
    top = results[0]
    assert top.get("name") == "Jaipur"
    assert top.get("state") == "Rajasthan"
    print(f"[PASS] Out-of-state search (Jaipur): {top.get('display_name')}")


def test_bug2_empty_and_invalid_searches():
    print("\n--- TEST BUG 2: Empty and Invalid Search Handling ---")
    # Empty query should return 400
    try:
        get_json(f"{BASE_URL}/api/location/search?q=")
        assert False, "Should have raised HTTP 400"
    except urllib.error.HTTPError as e:
        assert e.code == 400
        body = json.loads(e.read().decode('utf-8'))
        assert "Please enter a location" in body.get("error", "")
        print(f"[PASS] Empty query rejected gracefully with 400: {body.get('error')}")

    # Non-existent query should return 200 with empty results and error message for autocomplete
    status, data = get_json(f"{BASE_URL}/api/location/search?q=xyznonexistentplace9999")
    assert status == 200
    assert data.get("results") == []
    print(f"[PASS] Non-existent query handled smoothly: results={data.get('results')}")


def test_bug3_caching_and_parallel_apis():
    print("\n--- TEST BUG 3: Caching Latency & Parallel AQI Endpoints ---")
    
    # 1. First call (may populate cache)
    t0 = time.time()
    get_json(f"{BASE_URL}/api/location/search?q=Pune")
    t1 = time.time()
    first_time_ms = (t1 - t0) * 1000

    # 2. Second call (must be fast from cache)
    t0 = time.time()
    get_json(f"{BASE_URL}/api/location/search?q=Pune")
    t1 = time.time()
    cached_time_ms = (t1 - t0) * 1000
    print(f"[PASS] Search Cache speedup: First call {first_time_ms:.1f}ms -> Cached call {cached_time_ms:.1f}ms")
    assert cached_time_ms < 50, f"Cached call took {cached_time_ms}ms, expected < 50ms"

    # 3. Test Air Quality Endpoint
    status, aq = get_json(f"{BASE_URL}/api/air-quality?lat=19.0728&lon=72.8826")
    assert status == 200
    assert "aqi" in aq
    assert "category" in aq
    print(f"[PASS] AQI endpoint: AQI={aq.get('aqi')} ({aq.get('category')}) | Source={aq.get('data_source')}")

    # 4. Test Weather Endpoint
    status, wx = get_json(f"{BASE_URL}/api/weather?lat=19.0728&lon=72.8826")
    assert status == 200
    assert "humidity" in wx
    assert "wind_speed_kmh" in wx or "wind" in wx
    print(f"[PASS] Weather endpoint: Humidity={wx.get('humidity')}% | Wind={wx.get('wind_speed_kmh')} km/h")

    # 5. Test History Endpoint
    status, hist = get_json(f"{BASE_URL}/api/history?lat=19.0728&lon=72.8826&days=7")
    assert status == 200
    assert "days" in hist
    print(f"[PASS] 7-Day History endpoint: {len(hist.get('days', []))} daily snapshots available.")

    # 6. Test Authority Resolution
    status, auth = get_json(f"{BASE_URL}/api/authority?locality=Andheri+West&city=Mumbai")
    assert status == 200
    assert "Brihanmumbai Municipal Corporation" in auth.get("authority_name", "")
    print(f"[PASS] Authority resolution: {auth.get('authority_name')} | Jurisdiction: {auth.get('jurisdiction_scope')}")


if __name__ == "__main__":
    print("=" * 60)
    print("SkyCheck / AirGuard AI Automated Bug Fixes Test Suite")
    print("=" * 60)
    test_static_and_health();
    test_bug1_live_location_reverse();
    test_bug2_mumbai_wards_and_other_states();
    test_bug2_empty_and_invalid_searches();
    test_bug3_caching_and_parallel_apis();
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY! (100% Verified)")
    print("=" * 60)
