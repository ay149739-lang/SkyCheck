// ================================================================
// SkyCheck / AirGuard AI – Frontend Application Logic
// Feature A: Premium Historical AQI & Pollutant Analytics Dashboard
// Feature B: Location-Aware Government Environmental Complaint System
// ================================================================

// Support both same-origin (Flask served) and external dev servers (Live Server port 5500)
const API_BASE = (window.location.protocol.startsWith("http") && (window.location.port === "5000" || window.location.port === ""))
    ? window.location.origin
    : "http://127.0.0.1:5000";

const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

// ── Application State ───────────────────────────────────────────
let currentLocation = null;
let currentAqiData = null;
let currentWeatherData = null;
let currentAuthorityData = null;
let currentHistoryData = null;

let selectedHistoryDays = 7;
let selectedMetricTab = "aqi";
let aqiChartInstance = null;
let autoRefreshTimer = null;
let selectedPhotoBase64 = null;
let isSubmittingComplaint = false;
let isDetectingLocation = false;
let isRefreshing = false;
let noticeTimeout = null;

// Race-condition, cancellation & manual selection guards
let currentDashboardRequestId = 0;
let userHasSelectedManualLocation = false;
let dashboardAbortController = null;
let searchAbortController = null;
let searchDebounceTimer = null;

// Lightweight in-memory caches
const geoSearchCache = new Map(); // query -> results
const aqiDataCache = new Map();   // key(lat, lon, days) -> { aq, wx, hist, auth, ts }
const CACHE_VALIDITY_MS = 5 * 60 * 1000; // 5 minutes

// ── DOM Elements ────────────────────────────────────────────────
const menuToggleBtn = document.getElementById("menuToggleBtn");
const searchToggleBtn = document.getElementById("searchToggleBtn");
const headerLocationBtn = document.getElementById("headerLocationBtn");
const headerRefreshBtn = document.getElementById("headerRefreshBtn");
const useCurrentLocationBtn = document.getElementById("useCurrentLocationBtn");
const menuLocationBtn = document.getElementById("menuLocationBtn");

const locationTitleBtn = document.getElementById("locationTitleBtn");
const cityName = document.getElementById("cityName");
const liveGpsBadge = document.getElementById("liveGpsBadge");
const locationCoordsSubtitle = document.getElementById("locationCoordsSubtitle");

const locationNotice = document.getElementById("locationNotice");
const locationNoticeText = document.getElementById("locationNoticeText");
const dismissNoticeBtn = document.getElementById("dismissNoticeBtn");

const searchBarOverlay = document.getElementById("searchBarOverlay");
const cityInput = document.getElementById("cityInput");
const clearSearchBtn = document.getElementById("clearSearchBtn");
const locationDropdown = document.getElementById("locationDropdown");

// AQI Main Card
const aqiSummary = document.getElementById("aqiSummary");
const aqiPillFill = document.getElementById("aqiPillFill");

// 2x3 Weather Metrics Grid
const uvValue = document.getElementById("uvValue");
const humidityValue = document.getElementById("humidityValue");
const windValue = document.getElementById("windValue");
const windArrow = document.getElementById("windArrow");
const dewValue = document.getElementById("dewValue");
const pressureValue = document.getElementById("pressureValue");
const visibilityValue = document.getElementById("visibilityValue");

// Feature A: Historical Analytics Elements
const aqiChartCanvas = document.getElementById("aqiChart");
const statWeeklyAvg = document.getElementById("statWeeklyAvg");
const statWeeklyCat = document.getElementById("statWeeklyCat");
const statBestDay = document.getElementById("statBestDay");
const statBestVal = document.getElementById("statBestVal");
const statWorstDay = document.getElementById("statWorstDay");
const statWorstVal = document.getElementById("statWorstVal");
const statChangeVal = document.getElementById("statChangeVal");
const statChangeTrend = document.getElementById("statChangeTrend");
const statTrendLabel = document.getElementById("statTrendLabel");
const trendNarrativeText = document.getElementById("trendNarrativeText");
const dailyStripList = document.getElementById("dailyStripList");
const historyDataNote = document.getElementById("historyDataNote");

// Pollutant Elements
const pm25Val = document.getElementById("pm25Val");
const pm25Severity = document.getElementById("pm25Severity");
const pm10Val = document.getElementById("pm10Val");
const pm10Severity = document.getElementById("pm10Severity");
const no2Val = document.getElementById("no2Val");
const no2Severity = document.getElementById("no2Severity");
const so2Val = document.getElementById("so2Val");
const so2Severity = document.getElementById("so2Severity");
const coVal = document.getElementById("coVal");
const coSeverity = document.getElementById("coSeverity");
const o3Val = document.getElementById("o3Val");
const o3Severity = document.getElementById("o3Severity");
const nh3Val = document.getElementById("nh3Val");
const nh3Severity = document.getElementById("nh3Severity");

// Advisory Elements
const aiAdvisoryText = document.getElementById("aiAdvisoryText");
const lastUpdatedTag = document.getElementById("lastUpdatedTag");

// Feature B: Government Authority & Complaint Elements
const authorityNameDisplay = document.getElementById("authorityNameDisplay");
const authorityJurisdictionDisplay = document.getElementById("authorityJurisdictionDisplay");
const authorityRoutingNote = document.getElementById("authorityRoutingNote");
const authoritySourceLink = document.getElementById("authoritySourceLink");
const authorityVerifyDate = document.getElementById("authorityVerifyDate");
const authorityPortalLink = document.getElementById("authorityPortalLink");
const openComplaintModalBtn = document.getElementById("openComplaintModalBtn");
const mailStatus = document.getElementById("mailStatus");

// Complaint Modal Elements
const complaintModalOverlay = document.getElementById("complaintModalOverlay");
const closeComplaintModalBtn = document.getElementById("closeComplaintModalBtn");
const cancelComplaintBtn = document.getElementById("cancelComplaintBtn");
const testEmailBtn = document.getElementById("testEmailBtn");
const testEmailBtnText = document.getElementById("testEmailBtnText");
const submitComplaintBtn = document.getElementById("submitComplaintBtn");
const submitComplaintBtnText = document.getElementById("submitComplaintBtnText");
const complaintModalBody = document.getElementById("complaintModalBody");
const complaintModalFooter = document.getElementById("complaintModalFooter");
const modalSuccessView = document.getElementById("modalSuccessView");
const closeSuccessModalBtn = document.getElementById("closeSuccessModalBtn");
const modalStatusBanner = document.getElementById("modalStatusBanner");

// Form Inputs
const complaintUserName = document.getElementById("complaintUserName");
const complaintUserEmail = document.getElementById("complaintUserEmail");
const complaintLocationInput = document.getElementById("complaintLocationInput");
const complaintRecipientEmail = document.getElementById("complaintRecipientEmail");
const authoritySelector = document.getElementById("authoritySelector");
const authorityVerifyWarning = document.getElementById("authorityVerifyWarning");
const authorityVerifyBadge = document.getElementById("authorityVerifyBadge");
const complaintSourceSelect = document.getElementById("complaintSourceSelect");
const complaintDescInput = document.getElementById("complaintDescInput");
const charCountLabel = document.getElementById("charCountLabel");
const complaintConsentCheckbox = document.getElementById("complaintConsentCheckbox");
const complaintPhotoInput = document.getElementById("complaintPhotoInput");
const uploadDropZone = document.getElementById("uploadDropZone");
const uploadPrompt = document.getElementById("uploadPrompt");
const photoPreviewWrap = document.getElementById("photoPreviewWrap");
const photoPreviewImg = document.getElementById("photoPreviewImg");
const photoPreviewName = document.getElementById("photoPreviewName");
const removePhotoBtn = document.getElementById("removePhotoBtn");

// Modal Pre-fill Display
const modalLocName = document.getElementById("modalLocName");
const modalLocDetails = document.getElementById("modalLocDetails");
const modalAuthName = document.getElementById("modalAuthName");
const modalAuthRouting = document.getElementById("modalAuthRouting");
const modalAqiStrip = document.getElementById("modalAqiStrip");
const modalAqiBadge = document.getElementById("modalAqiBadge");
const modalAqiNum = document.getElementById("modalAqiNum");
const modalAqiCat = document.getElementById("modalAqiCat");
const modalPm25 = document.getElementById("modalPm25");
const modalPm10 = document.getElementById("modalPm10");
const modalTimestamp = document.getElementById("modalTimestamp");
const noAqiNotice = document.getElementById("noAqiNotice");
const aqiAvailabilityTag = document.getElementById("aqiAvailabilityTag");
const modalPortalLink = document.getElementById("modalPortalLink");
const successAuthorityName = document.getElementById("successAuthorityName");
const successRefId = document.getElementById("successRefId");
const copyRefIdBtn = document.getElementById("copyRefIdBtn");

// Fallback & Webmail Copy Elements
const fallbackTo = document.getElementById("fallbackTo");
const fallbackSubject = document.getElementById("fallbackSubject");
const fallbackBody = document.getElementById("fallbackBody");
const copyToBtn = document.getElementById("copyToBtn");
const copySubjectBtn = document.getElementById("copySubjectBtn");
const copyBodyBtn = document.getElementById("copyBodyBtn");
const copyAllDetailsBtn = document.getElementById("copyAllDetailsBtn");
const openGmailBtn = document.getElementById("openGmailBtn");
const openOutlookBtn = document.getElementById("openOutlookBtn");
const reopenMailtoBtn = document.getElementById("reopenMailtoBtn");
const backToEditBtn = document.getElementById("backToEditBtn");
const modalRefIdDisplay = document.getElementById("modalRefIdDisplay");
const refStorageLabel = document.getElementById("refStorageLabel");
const fallbackNoticeBox = document.getElementById("fallbackNoticeBox");
const civicStatusText = document.getElementById("civicStatusText");

let cachedAuthoritiesList = [];
let currentComplaintRefId = "";

// Drawer Menu Elements
const sideMenu = document.getElementById("sideMenu");
const closeMenuBtn = document.getElementById("closeMenuBtn");
const drawerBackdrop = document.getElementById("drawerBackdrop");
const drawerLastUpdated = document.getElementById("drawerLastUpdated");


// ── 1. Color & Category Helpers ─────────────────────────────────
function getCategoryColor(aqi, category) {
    if (aqi === null || aqi === undefined) return "#9e9e9e";
    const num = Number(aqi);
    if (num <= 50) return "#00b050";       // Good
    if (num <= 100) return "#8bc34a";      // Satisfactory
    if (num <= 200) return "#fbc02d";      // Moderate
    if (num <= 300) return "#ff7e00";      // Poor
    if (num <= 400) return "#e53935";      // Very Poor
    return "#880e4f";                      // Severe
}

function getCategoryName(aqi) {
    if (aqi === null || aqi === undefined) return "Unknown";
    const num = Number(aqi);
    if (num <= 50) return "Good";
    if (num <= 100) return "Satisfactory";
    if (num <= 200) return "Moderate";
    if (num <= 300) return "Poor";
    if (num <= 400) return "Very Poor";
    return "Severe";
}

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}


// ── Location Notice / Banner Helpers ─────────────────────────────
function showLocationNotice(message, type = "info", durationMs = 6000) {
    if (!locationNotice || !locationNoticeText) return;
    locationNotice.className = `location-notice-banner notice-${type}`;
    locationNoticeText.innerHTML = message;
    locationNotice.style.display = "flex";
    if (noticeTimeout) clearTimeout(noticeTimeout);
    if (durationMs > 0) {
        noticeTimeout = setTimeout(() => {
            hideLocationNotice();
        }, durationMs);
    }
}

function hideLocationNotice() {
    if (locationNotice) locationNotice.style.display = "none";
}

if (dismissNoticeBtn) {
    dismissNoticeBtn.addEventListener("click", hideLocationNotice);
}

// ── Geolocation & Live Detection ─────────────────────────────────
function getPositionWithFallback(onSuccess, onError) {
    let triedFallback = false;
    // Fast initial attempt with 6s timeout
    const highAccuracyOpts = { enableHighAccuracy: true, timeout: 6000, maximumAge: 60000 };
    // Standard accuracy fallback with 8s timeout and cached position allowance
    const lowAccuracyOpts = { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 };

    navigator.geolocation.getCurrentPosition(
        (pos) => onSuccess(pos),
        (err) => {
            // If user explicitly denied permission (code 1), do not retry
            if (err.code === 1) {
                onError(err);
                return;
            }
            // If timeout (code 3) or unavailable (code 2), retry with standard accuracy
            if (!triedFallback) {
                triedFallback = true;
                navigator.geolocation.getCurrentPosition(onSuccess, onError, lowAccuracyOpts);
            } else {
                onError(err);
            }
        },
        highAccuracyOpts
    );
}

async function requestUserLocation(isStartup = false) {
    if (isDetectingLocation) return;

    if (!("geolocation" in navigator)) {
        showLocationNotice("Geolocation is not supported by your browser. Please search for your city or area manually.", "warning", 8000);
        if (isStartup && !currentLocation) {
            searchLocation("CGS Colony", true);
        }
        return;
    }

    isDetectingLocation = true;
    if (!isStartup) {
        userHasSelectedManualLocation = false;
        showLocationNotice("<i class='fa-solid fa-spinner fa-spin'></i> Requesting browser GPS permission to detect your live location...", "info", 0);
    } else {
        showLocationNotice("<i class='fa-solid fa-location-crosshairs fa-spin'></i> Detecting your location to show local air quality...", "info", 6000);
    }
    headerLocationBtn?.classList.add("active");

    getPositionWithFallback(
        async (position) => {
            // Race condition guard: If user manually selected another location in the meantime, ignore delayed GPS
            if (isStartup && userHasSelectedManualLocation) {
                isDetectingLocation = false;
                headerLocationBtn?.classList.remove("active");
                return;
            }

            const lat = position.coords.latitude;
            const lon = position.coords.longitude;
            const acc = Math.round(position.coords.accuracy || 0);

            // Update top location display immediately
            cityName.innerText = "Resolving locality...";
            if (locationCoordsSubtitle) {
                locationCoordsSubtitle.innerText = `${lat.toFixed(3)}° N, ${lon.toFixed(3)}° E (±${acc}m) • Resolving station...`;
            }
            if (liveGpsBadge) {
                liveGpsBadge.style.display = "inline-flex";
            }

            try {
                // Reverse geocode coordinates
                const ctrl = new AbortController();
                const timeoutId = setTimeout(() => ctrl.abort(), 5000);
                const resp = await fetch(`${API_BASE}/api/location/reverse?lat=${lat}&lon=${lon}`, { signal: ctrl.signal });
                clearTimeout(timeoutId);

                const loc = await resp.json();
                if (!resp.ok || loc.error) {
                    throw new Error(loc.error || "Unable to resolve locality from coordinates.");
                }

                if (isStartup && userHasSelectedManualLocation) {
                    isDetectingLocation = false;
                    headerLocationBtn?.classList.remove("active");
                    return;
                }

                loc.is_live_gps = true;
                closeSearchOverlay();
                closeDrawer();

                await loadDashboardForLocation(loc);

                showLocationNotice(`<i class='fa-solid fa-circle-check'></i> Live GPS active: Monitoring air quality for <strong>${escapeHtml(loc.name || loc.locality)}</strong> (${lat.toFixed(3)}°, ${lon.toFixed(3)}°).`, "success", 4000);
                headerLocationBtn?.classList.add("active");
            } catch (err) {
                console.warn("Reverse geocode notice:", err);
                if (isStartup && userHasSelectedManualLocation) {
                    isDetectingLocation = false;
                    headerLocationBtn?.classList.remove("active");
                    return;
                }

                const fallbackLoc = {
                    name: `Live Location (${lat.toFixed(2)}°, ${lon.toFixed(2)}°)`,
                    locality: `Lat ${lat.toFixed(2)}, Lon ${lon.toFixed(2)}`,
                    city: "",
                    district: "",
                    state: "",
                    country: "India",
                    country_code: "IN",
                    latitude: lat,
                    longitude: lon,
                    display_name: `Coordinates: ${lat.toFixed(4)}, ${lon.toFixed(4)}`,
                    is_live_gps: true
                };
                closeSearchOverlay();
                closeDrawer();
                await loadDashboardForLocation(fallbackLoc);
                showLocationNotice(`Monitoring live coordinates: ${lat.toFixed(3)}°, ${lon.toFixed(3)}°`, "success", 4000);
                headerLocationBtn?.classList.add("active");
            } finally {
                isDetectingLocation = false;
            }
        },
        (err) => {
            isDetectingLocation = false;
            headerLocationBtn?.classList.remove("active");
            if (liveGpsBadge) liveGpsBadge.style.display = "none";

            let errMsg = "Unable to retrieve your location.";
            let type = "warning";

            if (err.code === 1) { // PERMISSION_DENIED
                errMsg = "<strong>Location permission denied.</strong> SkyCheck needs permission to detect nearby air quality. You can search for your city or area manually above.";
            } else if (err.code === 2) { // POSITION_UNAVAILABLE
                errMsg = "<strong>Location unavailable.</strong> Device could not determine GPS fix. Ensure location services are enabled, or search manually.";
            } else if (err.code === 3) { // TIMEOUT
                errMsg = "<strong>Location request timed out.</strong> GPS took too long to respond. Tap <a href='#' id='retryGpsBtn' style='color:#60a5fa;text-decoration:underline;font-weight:600;'>Retry Live Location</a> or search manually.";
            }

            showLocationNotice(errMsg, type, 8000);
            document.getElementById("retryGpsBtn")?.addEventListener("click", (e) => {
                e.preventDefault();
                requestUserLocation(false);
            });

            if (isStartup && !currentLocation) {
                searchLocation("CGS Colony", true);
            }
        }
    );
}

// ── Refresh Dashboard Helper ─────────────────────────────────────
async function refreshDashboard() {
    if (isRefreshing || !currentLocation) return;
    isRefreshing = true;

    const spinIcons = document.querySelectorAll("#headerRefreshBtn i, #menuRefreshBtn i");
    spinIcons.forEach(icon => icon.classList.add("fa-spin"));

    try {
        await loadDashboardForLocation(currentLocation, true);
        showLocationNotice(`<i class="fa-solid fa-arrows-rotate"></i> Data refreshed successfully for ${escapeHtml(currentLocation.name || currentLocation.locality)}.`, "success", 3000);
    } finally {
        setTimeout(() => {
            spinIcons.forEach(icon => icon.classList.remove("fa-spin"));
            isRefreshing = false;
        }, 500);
    }
}

// ── 2. Search & Location Selection ──────────────────────────────
async function searchLocation(query, autoSelectFirst = false) {
    if (!query) return;
    const cleanQuery = query.trim();
    if (!cleanQuery) return;

    userHasSelectedManualLocation = true;

    // Fast check: In-memory geocoding cache
    const cacheKey = cleanQuery.toLowerCase();
    const cachedResults = geoSearchCache.get(cacheKey);
    if (cachedResults && cachedResults.length > 0) {
        if (autoSelectFirst || cachedResults.length === 1) {
            closeSearchOverlay();
            loadDashboardForLocation(cachedResults[0]);
            return;
        } else {
            openSearchOverlay();
            showLocationDropdown(cachedResults);
            return;
        }
    }

    // Immediately update header title & status to selected search text so previous location is not left visible
    cityName.innerText = cleanQuery;
    if (locationCoordsSubtitle) {
        locationCoordsSubtitle.innerText = "Searching location coordinates...";
    }
    if (liveGpsBadge) {
        liveGpsBadge.style.display = "none";
    }
    headerLocationBtn?.classList.remove("active");
    aqiSummary.innerText = "Searching...";

    try {
        const resp = await fetch(`${API_BASE}/api/location/search?q=${encodeURIComponent(cleanQuery)}&count=6`);
        const data = await resp.json();

        if (!resp.ok || (data.error && (!data.results || data.results.length === 0))) {
            showLocationNotice(data.error || `Location "${escapeHtml(cleanQuery)}" not found.`, "warning", 6000);
            aqiSummary.innerText = "Not Found";
            return;
        }

        const results = data.results || [];
        if (results.length === 0) {
            showLocationNotice(`No locations found for "${escapeHtml(cleanQuery)}". Please try a nearby city, area or ward.`, "warning", 6000);
            aqiSummary.innerText = "No Match";
            return;
        }

        geoSearchCache.set(cacheKey, results);

        if (results.length === 1 || autoSelectFirst) {
            closeSearchOverlay();
            loadDashboardForLocation(results[0]);
        } else {
            openSearchOverlay();
            showLocationDropdown(results);
        }
    } catch (err) {
        console.error("Search error:", err);
        showLocationNotice("Cannot reach SkyCheck backend server. Ensure backend is running on port 5000.", "error", 6000);
        aqiSummary.innerText = "Offline";
    }
}

// Debounced autocomplete suggestions as user types
async function handleSearchInput(query) {
    const qClean = (query || "").trim();
    if (!qClean || qClean.length < 2) {
        closeLocationDropdown();
        return;
    }

    const qLower = qClean.toLowerCase();
    const cached = geoSearchCache.get(qLower);
    if (cached) {
        showLocationDropdown(cached);
        return;
    }

    // Show smooth inline searching feedback inside dropdown
    locationDropdown.innerHTML = `
        <div class="location-option-item" style="display:flex;align-items:center;gap:8px;color:rgba(255,255,255,0.7);cursor:default;">
            <i class="fa-solid fa-spinner fa-spin"></i> Searching locations...
        </div>
    `;

    if (searchAbortController) {
        searchAbortController.abort();
    }
    searchAbortController = new AbortController();

    try {
        const resp = await fetch(`${API_BASE}/api/location/search?q=${encodeURIComponent(qClean)}&count=6`, {
            signal: searchAbortController.signal
        });
        const data = await resp.json();
        const results = data.results || [];

        geoSearchCache.set(qLower, results);

        if (results.length > 0) {
            showLocationDropdown(results);
        } else {
            locationDropdown.innerHTML = `
                <div class="location-option-item" style="color:rgba(255,255,255,0.6);cursor:default;">
                    No matching cities or wards found for "${escapeHtml(qClean)}"
                </div>
            `;
        }
    } catch (err) {
        if (err.name === "AbortError") return;
        console.warn("Autocomplete error:", err);
    }
}

function showLocationDropdown(results) {
    locationDropdown.innerHTML = "";
    results.forEach(loc => {
        const item = document.createElement("div");
        item.className = "location-option-item";
        const primary = loc.name || loc.locality || "Location";
        item.innerHTML = `
            <div class="location-option-name">${escapeHtml(primary)}</div>
            <div class="location-option-sub">${escapeHtml(loc.display_name || "")}</div>
        `;
        item.addEventListener("click", () => {
            userHasSelectedManualLocation = true;
            closeSearchOverlay();
            cityInput.value = primary;
            loadDashboardForLocation(loc);
        });
        locationDropdown.appendChild(item);
    });
}

function closeLocationDropdown() {
    locationDropdown.innerHTML = "";
}

function openSearchOverlay() {
    searchBarOverlay.classList.add("show");
    cityInput.focus();
}

function closeSearchOverlay() {
    searchBarOverlay.classList.remove("show");
    closeLocationDropdown();
}


// ── 3. Load Complete Dashboard Data ─────────────────────────────
async function loadDashboardForLocation(loc, isRefresh = false) {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }

    // Increment request token to prevent stale out-of-order responses from overwriting latest result
    const thisRequestId = ++currentDashboardRequestId;

    // Abort any ongoing dashboard fetches
    if (dashboardAbortController) {
        dashboardAbortController.abort();
    }
    dashboardAbortController = new AbortController();
    const signal = dashboardAbortController.signal;

    currentLocation = loc;
    const primaryName = loc.name || loc.locality || "Location";

    // 1. Immediately update top location header & coordinates to selected result
    cityName.innerText = primaryName;
    const lat = loc.latitude;
    const lon = loc.longitude;
    const latVal = Number(lat);
    const lonVal = Number(lon);
    const latStr = !isNaN(latVal) ? `${latVal.toFixed(3)}° N` : "";
    const lonStr = !isNaN(lonVal) ? `${lonVal.toFixed(3)}° E` : "";
    const liveMarker = loc.is_live_gps ? " • Live GPS" : "";

    if (locationCoordsSubtitle) {
        locationCoordsSubtitle.innerText = `${latStr}, ${lonStr}${liveMarker} • Fetching atmospheric data...`;
    }
    if (liveGpsBadge) {
        liveGpsBadge.style.display = loc.is_live_gps ? "inline-flex" : "none";
    }
    if (headerLocationBtn) {
        if (loc.is_live_gps) {
            headerLocationBtn.classList.add("active");
        } else {
            headerLocationBtn.classList.remove("active");
        }
    }

    // Set clear loading state on AQI card
    aqiSummary.innerText = "Loading AQI...";
    aqiPillFill.style.width = "20%";
    aqiPillFill.style.backgroundColor = "#9e9e9e";

    // 2. Check Client-Side Cache
    const cacheKey = `${latVal.toFixed(3)}|${lonVal.toFixed(3)}|${selectedHistoryDays}`;
    const cachedEntry = aqiDataCache.get(cacheKey);
    if (!isRefresh && cachedEntry && (Date.now() - cachedEntry.ts < CACHE_VALIDITY_MS)) {
        currentAqiData = cachedEntry.aq;
        currentWeatherData = cachedEntry.wx;
        currentHistoryData = cachedEntry.hist;
        currentAuthorityData = cachedEntry.auth;

        renderDashboard();
        startAutoRefresh(loc);
        return;
    }

    const locNameParam = encodeURIComponent(primaryName);
    const refreshQuery = isRefresh ? "&refresh=1" : "";

    try {
        // Kick off independent API requests in parallel
        const aqPromise = fetch(`${API_BASE}/api/air-quality?lat=${lat}&lon=${lon}&location_name=${locNameParam}${refreshQuery}`, { signal }).then(r => r.json());
        const wxPromise = fetch(`${API_BASE}/api/weather?lat=${lat}&lon=${lon}${refreshQuery}`, { signal }).then(r => r.json());
        const histPromise = fetch(`${API_BASE}/api/history?lat=${lat}&lon=${lon}&days=${selectedHistoryDays}&location_name=${locNameParam}${refreshQuery}`, { signal }).then(r => r.json());
        const authPromise = fetch(`${API_BASE}/api/authority?locality=${encodeURIComponent(loc.locality || loc.name || '')}&city=${encodeURIComponent(loc.city || '')}&district=${encodeURIComponent(loc.district || '')}&state=${encodeURIComponent(loc.state || '')}&display_name=${encodeURIComponent(loc.display_name || '')}`, { signal }).then(r => r.json());

        // Progressive Rendering: Render primary AQI, weather, pollutants and advisory as soon as AQ & Weather arrive!
        Promise.all([aqPromise, wxPromise]).then(([aqRes, wxRes]) => {
            if (thisRequestId !== currentDashboardRequestId) return;
            currentAqiData = aqRes;
            currentWeatherData = wxRes;
            renderAqiAndWeatherCards();
        }).catch(err => {
            if (err.name === "AbortError" || thisRequestId !== currentDashboardRequestId) return;
            console.error("AQ/WX load error:", err);
            aqiSummary.innerText = "Data Unavailable";
        });

        // Render Historical 7-day Analytics as soon as history completes
        histPromise.then(histRes => {
            if (thisRequestId !== currentDashboardRequestId) return;
            currentHistoryData = histRes;
            renderHistoricalAnalytics(histRes);
        }).catch(err => {
            if (err.name === "AbortError" || thisRequestId !== currentDashboardRequestId) return;
            console.warn("History load notice:", err);
        });

        // Render Authority Section as soon as authority completes
        authPromise.then(authRes => {
            if (thisRequestId !== currentDashboardRequestId) return;
            currentAuthorityData = authRes;
            renderAuthority(authRes);
        }).catch(err => {
            if (err.name === "AbortError" || thisRequestId !== currentDashboardRequestId) return;
            console.warn("Authority load notice:", err);
        });

        // When all promises settle, cache combined data and start auto-refresh
        const [aqFinal, wxFinal, histFinal, authFinal] = await Promise.all([
            aqPromise, wxPromise, histPromise, authPromise
        ]);

        if (thisRequestId !== currentDashboardRequestId) return;

        currentAqiData = aqFinal;
        currentWeatherData = wxFinal;
        currentHistoryData = histFinal;
        currentAuthorityData = authFinal;

        aqiDataCache.set(cacheKey, {
            aq: aqFinal,
            wx: wxFinal,
            hist: histFinal,
            auth: authFinal,
            ts: Date.now()
        });

        startAutoRefresh(loc);
    } catch (err) {
        if (err.name === "AbortError") return;
        console.error("Dashboard load failure:", err);
        if (thisRequestId === currentDashboardRequestId) {
            aqiSummary.innerText = "Unavailable";
            if (locationCoordsSubtitle) {
                locationCoordsSubtitle.innerText = `${latStr}, ${lonStr} • Connection error`;
            }
        }
    }
}

function renderAqiAndWeatherCards() {
    if (!currentAqiData || !currentWeatherData) return;

    const aq = currentAqiData;
    const wx = currentWeatherData;

    // Subtitle data source update
    if (currentLocation && locationCoordsSubtitle) {
        const latVal = Number(currentLocation.latitude);
        const lonVal = Number(currentLocation.longitude);
        const latStr = !isNaN(latVal) ? `${latVal.toFixed(3)}° N` : "";
        const lonStr = !isNaN(lonVal) ? `${lonVal.toFixed(3)}° E` : "";
        const srcStr = aq.data_source || "Open-Meteo Air Quality";
        const liveMarker = currentLocation.is_live_gps ? " • Live GPS" : "";
        locationCoordsSubtitle.innerText = `${latStr}, ${lonStr} • ${srcStr}${liveMarker}`;
    }

    // 1. AQI Indicator Card
    const aqiVal = aq.aqi;
    const cat = aq.category || getCategoryName(aqiVal);
    const col = getCategoryColor(aqiVal, cat);

    if (aqiVal !== null && aqiVal !== undefined) {
        aqiSummary.innerText = `${cat} (${aqiVal})`;
        const maxScale = 500;
        const pct = Math.min(100, Math.max(8, (Number(aqiVal) / maxScale) * 100));
        aqiPillFill.style.width = `${pct}%`;
        aqiPillFill.style.backgroundColor = col;
    } else {
        aqiSummary.innerText = `${cat} (--)`;
        aqiPillFill.style.width = "10%";
        aqiPillFill.style.backgroundColor = "#ff9100";
    }

    // 2. Weather Metrics Grid
    uvValue.innerText = wx.uv_category || (wx.uv_index !== undefined ? `Level ${wx.uv_index}` : "Moderate");
    humidityValue.innerText = (wx.humidity !== undefined && wx.humidity !== null) ? `${wx.humidity}%` : "48%";

    const windKmh = (wx.wind_speed_kmh !== undefined && wx.wind_speed_kmh !== null)
        ? wx.wind_speed_kmh
        : (wx.wind ? Math.round(wx.wind * 3.6) : 11);
    windValue.innerText = `${windKmh} km/h`;
    if (wx.wind_deg !== undefined && wx.wind_deg !== null) {
        windArrow.style.transform = `rotate(${wx.wind_deg + 45}deg)`;
    }

    dewValue.innerText = (wx.dew_point !== undefined && wx.dew_point !== null)
        ? `${Math.round(wx.dew_point)}°`
        : "21°";
    pressureValue.innerText = (wx.pressure !== undefined && wx.pressure !== null)
        ? `${wx.pressure} mb`
        : "1011 mb";
    visibilityValue.innerText = (wx.visibility !== undefined && wx.visibility !== null)
        ? `${wx.visibility} km`
        : "2.5 km";

    // 3. Pollutants Breakdown
    renderPollutants(aq);

    // 4. AI Health Advisory
    renderAdvisory(aq);

    // 5. Timestamps
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    lastUpdatedTag.innerText = `Updated ${timeStr}`;
    drawerLastUpdated.innerText = `Last updated: ${timeStr}`;
}

function renderDashboard() {
    renderAqiAndWeatherCards();
    if (currentHistoryData) {
        renderHistoricalAnalytics(currentHistoryData);
    }
    if (currentAuthorityData) {
        renderAuthority(currentAuthorityData);
    }
}


// ── 4. FEATURE A: Premium Historical Analytics & Time-Series ────
function renderHistoricalAnalytics(historyObj) {
    if (!historyObj || !historyObj.available || !historyObj.days || historyObj.days.length === 0) {
        historyDataNote.innerText = historyObj?.note || "Historical readings recorded as persistent snapshots";
        trendNarrativeText.innerText = "Atmospheric history is accumulating for this geographical coordinate.";
        return;
    }

    historyDataNote.innerText = historyObj.note || "Live atmospheric observation network";

    const days = [...historyObj.days];
    const summary = historyObj.summary || {};
    const comp = historyObj.completeness || {};

    // Update range badge
    const rangeBadge = document.getElementById("historyCoverageBadge");
    if (rangeBadge) {
        rangeBadge.innerText = comp.label || `${days.length} Days Recorded`;
    }

    // 1. Period Statistics Grid
    const periodAvg = summary.period_avg ?? summary.weekly_avg ?? "--";
    statWeeklyAvg.innerText = periodAvg;
    statWeeklyCat.innerText = getCategoryName(periodAvg);

    if (summary.best_day) {
        statBestDay.innerText = `${summary.best_day.day || ''} ${summary.best_day.date || ''}`.trim();
        statBestVal.innerText = `${summary.best_day.aqi} (${summary.best_day.category || getCategoryName(summary.best_day.aqi)})`;
    }

    if (summary.worst_day) {
        statWorstDay.innerText = `${summary.worst_day.day || ''} ${summary.worst_day.date || ''}`.trim();
        statWorstVal.innerText = `${summary.worst_day.aqi} (${summary.worst_day.category || getCategoryName(summary.worst_day.aqi)})`;
    }

    // Trend & Change
    statTrendLabel.innerText = `${selectedHistoryDays}D Trend & Change`;
    const pctChange = summary.pct_change;
    const dayChange = summary.day_change;
    const trend = summary.trend || "stable";

    if (pctChange !== undefined && pctChange !== null) {
        const sign = pctChange > 0 ? "+" : "";
        statChangeVal.innerText = `${sign}${pctChange}%`;
    } else {
        const sign = (dayChange > 0) ? "+" : "";
        statChangeVal.innerText = `${sign}${dayChange || 0}`;
    }

    if (trend === "improving") {
        statChangeTrend.innerText = "▼ Improving";
        statChangeTrend.className = "stat-sub text-good";
    } else if (trend === "worsening") {
        statChangeTrend.innerText = "▲ Worsening";
        statChangeTrend.className = "stat-sub text-severe";
    } else {
        statChangeTrend.innerText = "● Stable";
        statChangeTrend.className = "stat-sub text-mod";
    }

    // Trend Narrative
    trendNarrativeText.innerText = summary.trend_narrative ||
        `Atmospheric observations tracked across ${days.length} days for ${cityName.innerText}.`;

    // 2. Render Daily Breakdown Strip
    dailyStripList.innerHTML = "";
    days.forEach((d, idx) => {
        const isToday = idx === days.length - 1;
        const aqiVal = d.aqi !== null ? d.aqi : "--";
        const cat = d.category || getCategoryName(d.aqi);
        const col = d.color || getCategoryColor(d.aqi, cat);
        const pm25Text = d.pm25 !== undefined && d.pm25 !== null ? `PM2.5: ${d.pm25}` : "";

        const item = document.createElement("div");
        item.className = `daily-strip-item ${isToday ? 'today' : ''}`;
        item.innerHTML = `
            <span class="daily-day-label">${isToday ? 'Today' : (d.day || d.date.split(' ')[0])}</span>
            <span class="daily-date-label">${d.date}</span>
            <span class="daily-aqi-badge" style="background-color: ${col};">${aqiVal}</span>
            <span class="daily-cat-label" title="${cat}">${cat}</span>
            ${pm25Text ? `<span class="daily-metric-sub">${pm25Text}</span>` : ''}
        `;
        dailyStripList.appendChild(item);
    });

    // 3. Render Chart.js Visualization
    renderAqiChart(days, selectedMetricTab);
}

function renderAqiChart(days, metricType = "aqi") {
    if (!aqiChartCanvas) return;

    if (aqiChartInstance) {
        aqiChartInstance.destroy();
        aqiChartInstance = null;
    }

    const labels = days.map((d, i) =>
        i === days.length - 1 ? "Today" : (d.day ? `${d.day} ${d.date.split(' ')[1] || ''}`.trim() : d.date)
    );

    const ctx = aqiChartCanvas.getContext("2d");
    const datasets = [];

    if (metricType === "aqi") {
        const dataVals = days.map(d => d.aqi);
        const pointColors = days.map(d => d.color || getCategoryColor(d.aqi, d.category));

        const gradient = ctx.createLinearGradient(0, 0, 0, 200);
        gradient.addColorStop(0, "rgba(255, 126, 0, 0.35)");
        gradient.addColorStop(0.6, "rgba(255, 126, 0, 0.08)");
        gradient.addColorStop(1, "rgba(255, 126, 0, 0.0)");

        datasets.push({
            label: "AQI",
            data: dataVals,
            borderColor: "#ffffff",
            borderWidth: 2.8,
            backgroundColor: gradient,
            fill: true,
            tension: 0.36,
            pointBackgroundColor: pointColors,
            pointBorderColor: "#ffffff",
            pointBorderWidth: 2,
            pointRadius: 5.5,
            pointHoverRadius: 8,
            pointHoverBackgroundColor: "#ffffff",
            pointHoverBorderColor: pointColors,
            pointHoverBorderWidth: 3
        });
    } else if (metricType === "pm25") {
        const dataVals = days.map(d => d.pm25 ?? null);
        const gradient = ctx.createLinearGradient(0, 0, 0, 200);
        gradient.addColorStop(0, "rgba(96, 165, 250, 0.4)");
        gradient.addColorStop(1, "rgba(96, 165, 250, 0.0)");

        datasets.push({
            label: "PM2.5 (µg/m³)",
            data: dataVals,
            borderColor: "#60a5fa",
            borderWidth: 2.8,
            backgroundColor: gradient,
            fill: true,
            tension: 0.36,
            pointBackgroundColor: "#93c5fd",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 2,
            pointRadius: 5.5,
            pointHoverRadius: 8
        });
    } else if (metricType === "pm10") {
        const dataVals = days.map(d => d.pm10 ?? null);
        const gradient = ctx.createLinearGradient(0, 0, 0, 200);
        gradient.addColorStop(0, "rgba(251, 146, 60, 0.4)");
        gradient.addColorStop(1, "rgba(251, 146, 60, 0.0)");

        datasets.push({
            label: "PM10 (µg/m³)",
            data: dataVals,
            borderColor: "#fb923c",
            borderWidth: 2.8,
            backgroundColor: gradient,
            fill: true,
            tension: 0.36,
            pointBackgroundColor: "#fdba74",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 2,
            pointRadius: 5.5,
            pointHoverRadius: 8
        });
    } else if (metricType === "compare") {
        // Multi-Metric Comparison Overlay
        datasets.push({
            label: "AQI",
            data: days.map(d => d.aqi),
            borderColor: "#ffffff",
            borderWidth: 2.4,
            fill: false,
            tension: 0.35,
            pointBackgroundColor: days.map(d => d.color || getCategoryColor(d.aqi, d.category)),
            pointRadius: 4.5
        });
        datasets.push({
            label: "PM2.5",
            data: days.map(d => d.pm25 ?? null),
            borderColor: "#60a5fa",
            borderWidth: 2.2,
            borderDash: [5, 4],
            fill: false,
            tension: 0.35,
            pointBackgroundColor: "#60a5fa",
            pointRadius: 4.5
        });
        datasets.push({
            label: "PM10",
            data: days.map(d => d.pm10 ?? null),
            borderColor: "#fb923c",
            borderWidth: 2.2,
            borderDash: [3, 3],
            fill: false,
            tension: 0.35,
            pointBackgroundColor: "#fb923c",
            pointRadius: 4.5
        });
    }

    aqiChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: { top: 12, bottom: 6, left: 6, right: 12 }
            },
            interaction: {
                intersect: false,
                mode: "index"
            },
            plugins: {
                legend: {
                    display: metricType === "compare",
                    labels: {
                        color: "rgba(255, 255, 255, 0.85)",
                        font: { family: "Plus Jakarta Sans", size: 11, weight: "600" },
                        boxWidth: 12
                    }
                },
                tooltip: {
                    backgroundColor: "rgba(15, 28, 56, 0.95)",
                    titleColor: "#ffffff",
                    bodyColor: "#ffffff",
                    borderColor: "rgba(255, 255, 255, 0.22)",
                    borderWidth: 1,
                    padding: 12,
                    cornerRadius: 14,
                    displayColors: metricType === "compare",
                    callbacks: {
                        title: function (items) {
                            const idx = items[0].dataIndex;
                            const d = days[idx];
                            return `${d.day || ''} ${d.date || ''}`.trim();
                        },
                        label: function (context) {
                            const val = context.raw;
                            if (val === null || val === undefined) return `${context.dataset.label}: Unavailable`;
                            if (context.dataset.label === "AQI") {
                                const cat = getCategoryName(val);
                                return `AQI: ${val} (${cat})`;
                            }
                            return `${context.dataset.label}: ${val} µg/m³`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: "rgba(255, 255, 255, 0.08)",
                        drawBorder: false
                    },
                    ticks: {
                        color: "rgba(255, 255, 255, 0.82)",
                        font: { family: "Plus Jakarta Sans", size: 11, weight: "500" }
                    }
                },
                y: {
                    min: 0,
                    suggestedMax: 300,
                    grid: {
                        color: "rgba(255, 255, 255, 0.08)",
                        drawBorder: false
                    },
                    ticks: {
                        color: "rgba(255, 255, 255, 0.82)",
                        font: { family: "Plus Jakarta Sans", size: 10.5 },
                        stepSize: 75
                    }
                }
            }
        }
    });
}

// Range Buttons Click Handlers
document.querySelectorAll(".range-pill").forEach(btn => {
    btn.addEventListener("click", async () => {
        document.querySelectorAll(".range-pill").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        selectedHistoryDays = parseInt(btn.getAttribute("data-days"), 10) || 7;

        if (currentLocation) {
            try {
                historyDataNote.innerText = "Fetching extended historical analytics...";
                const res = await fetch(`${API_BASE}/api/history?lat=${currentLocation.latitude}&lon=${currentLocation.longitude}&days=${selectedHistoryDays}`);
                const data = await res.json();
                currentHistoryData = data;
                renderHistoricalAnalytics(data);
            } catch (err) {
                console.error("Failed to fetch extended history:", err);
            }
        }
    });
});

// Metric Tabs Click Handlers
document.querySelectorAll(".metric-tab-pill").forEach(tab => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".metric-tab-pill").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        selectedMetricTab = tab.getAttribute("data-metric") || "aqi";

        if (currentHistoryData && currentHistoryData.days) {
            renderAqiChart(currentHistoryData.days, selectedMetricTab);
        }
    });
});


// ── 5. Render Pollutants with Dynamic Severity Badges ───────────
function renderPollutants(aq) {
    const p = aq.pollutants || {};

    const updatePill = (el, sevEl, val, pillId, thresholds) => {
        const pill = document.getElementById(pillId);
        if (!pill) return;
        if (val !== undefined && val !== null) {
            el.innerText = `${val}`;
            pill.style.display = "flex";

            if (sevEl && thresholds) {
                const num = Number(val);
                if (num <= thresholds.good) {
                    sevEl.innerText = "Good";
                    sevEl.className = "p-sev-badge sev-good";
                } else if (num <= thresholds.mod) {
                    sevEl.innerText = "Moderate";
                    sevEl.className = "p-sev-badge sev-mod";
                } else if (num <= thresholds.poor) {
                    sevEl.innerText = "Poor";
                    sevEl.className = "p-sev-badge sev-poor";
                } else {
                    sevEl.innerText = "Severe";
                    sevEl.className = "p-sev-badge sev-severe";
                }
            }
        } else {
            pill.style.display = "none";
        }
    };

    updatePill(pm25Val, pm25Severity, p.pm25 ?? aq.pm25, "pPill_pm25", { good: 30, mod: 60, poor: 90 });
    updatePill(pm10Val, pm10Severity, p.pm10 ?? aq.pm10, "pPill_pm10", { good: 50, mod: 100, poor: 250 });
    updatePill(no2Val, no2Severity, p.no2 ?? aq.no2, "pPill_no2", { good: 40, mod: 80, poor: 180 });
    updatePill(so2Val, so2Severity, p.so2 ?? aq.so2, "pPill_so2", { good: 40, mod: 80, poor: 380 });
    updatePill(coVal, coSeverity, p.co ?? aq.co, "pPill_co", { good: 1.0, mod: 2.0, poor: 10.0 });
    updatePill(o3Val, o3Severity, p.o3 ?? aq.o3, "pPill_o3", { good: 50, mod: 100, poor: 168 });
    updatePill(nh3Val, nh3Severity, p.nh3 ?? aq.nh3, "pPill_nh3", { good: 200, mod: 400, poor: 800 });
}


// ── 6. Render AI Health Recommendations ─────────────────────────
function renderAdvisory(aq) {
    let text = aq.health_advice || "";
    if (aq.recommendation) {
        text += " " + aq.recommendation;
    }
    aiAdvisoryText.innerText = text || "Maintain adequate indoor ventilation and monitor local outdoor emissions.";
}


// ── 7. FEATURE B: Render Authority & Location Routing ───────────
function renderAuthority(auth) {
    if (!auth) return;

    authorityNameDisplay.innerText = auth.authority_name || "Environmental Authority";
    authorityJurisdictionDisplay.innerText = `Jurisdiction: ${auth.jurisdiction_scope || auth.city || "Local Area"}`;
    authorityRoutingNote.innerText = auth.routing_explanation || "Verified official environmental authority.";

    if (auth.official_source_url) {
        authoritySourceLink.href = auth.official_source_url;
        try {
            const domain = new URL(auth.official_source_url).hostname;
            authoritySourceLink.innerText = domain;
        } catch {
            authoritySourceLink.innerText = "Official Government Source";
        }
    }

    if (auth.verification_date) {
        authorityVerifyDate.innerText = `Verified: ${auth.verification_date}`;
    }

    if (auth.portal_url) {
        authorityPortalLink.href = auth.portal_url;
        authorityPortalLink.style.display = "inline-flex";
    } else {
        authorityPortalLink.style.display = "none";
    }
}


// ── 8. FEATURE B: User-Driven Prefilled Complaint Workflow ───────

async function loadAuthoritiesDirectory() {
    if (cachedAuthoritiesList && cachedAuthoritiesList.length > 0) return cachedAuthoritiesList;
    try {
        const resp = await fetch(`${API_BASE}/api/authorities`);
        if (resp.ok) {
            const data = await resp.json();
            if (data.success && Array.isArray(data.authorities)) {
                cachedAuthoritiesList = data.authorities;
                populateAuthorityDropdown();
            }
        }
    } catch (e) {
        console.warn("Could not fetch authorities directory:", e);
    }
    return cachedAuthoritiesList;
}

function populateAuthorityDropdown() {
    if (!authoritySelector || cachedAuthoritiesList.length === 0) return;
    const currentVal = authoritySelector.value;
    authoritySelector.innerHTML = '<option value="">-- Keep Auto-Resolved Authority --</option>';

    cachedAuthoritiesList.forEach(auth => {
        const opt = document.createElement("option");
        opt.value = auth.id;
        const scope = auth.ward_code ? `Ward ${auth.ward_code}` : (auth.jurisdiction_scope || auth.city || auth.state || "Jurisdiction");
        opt.textContent = `${auth.authority_name} (${scope})`;
        authoritySelector.appendChild(opt);
    });

    if (currentVal) authoritySelector.value = currentVal;
}

function syncAuthorityUi(auth) {
    if (!auth) return;

    if (modalAuthName) modalAuthName.innerText = auth.authority_name || "Designated Environmental Authority";
    if (modalAuthRouting) modalAuthRouting.innerText = `Jurisdiction: ${auth.jurisdiction_scope || auth.city || 'Local Area'}`;

    if (auth.portal_url && modalPortalLink) {
        modalPortalLink.href = auth.portal_url;
        const wrap = document.getElementById("modalPortalLinkWrap");
        if (wrap) wrap.style.display = "block";
    }

    const hasEmail = Boolean(auth.email && String(auth.email).includes("@"));
    const isVerified = Boolean(hasEmail && auth.verification_status !== "unverified" && auth.email_available !== false);

    if (isVerified) {
        if (complaintRecipientEmail) complaintRecipientEmail.value = auth.email;
        if (authorityVerifyBadge) {
            authorityVerifyBadge.innerText = "Verified Authority";
            authorityVerifyBadge.style.background = "rgba(16, 185, 129, 0.2)";
            authorityVerifyBadge.style.color = "#6ee7b7";
        }
        if (authorityVerifyWarning) authorityVerifyWarning.style.display = "none";
    } else {
        if (complaintRecipientEmail) complaintRecipientEmail.value = auth.email || "";
        if (authorityVerifyBadge) {
            authorityVerifyBadge.innerText = "Unverified / Missing";
            authorityVerifyBadge.style.background = "rgba(239, 68, 68, 0.2)";
            authorityVerifyBadge.style.color = "#fca5a5";
        }
        if (authorityVerifyWarning) authorityVerifyWarning.style.display = "flex";
    }
}

function generateProvisionalRefId() {
    return "SKY-" + new Date().getFullYear() + "-" + Math.floor(10000 + Math.random() * 90000);
}

function updateDraftPreview() {
    const name = (complaintUserName?.value || "").trim();
    const email = (complaintUserEmail?.value || "").trim();
    const locInput = (complaintLocationInput?.value || "").trim();
    const recipient = (complaintRecipientEmail?.value || "").trim();
    const source = complaintSourceSelect?.value || "General Environmental Issue";
    const desc = (complaintDescInput?.value || "").trim();

    if (!currentComplaintRefId) {
        currentComplaintRefId = generateProvisionalRefId();
    }

    if (modalRefIdDisplay) {
        modalRefIdDisplay.innerText = currentComplaintRefId;
    }

    const complaint = buildComplaintContent({
        name: name || "Citizen Complainant",
        email: email,
        locationName: locInput || (currentLocation?.name || "Incident Location"),
        locationData: currentLocation,
        recipientEmail: recipient,
        source: source,
        description: desc || "[Citizen complaint details will appear here as entered above...]",
        aqiData: currentAqiData,
        weatherData: currentWeatherData,
        authorityData: currentAuthorityData,
        refId: currentComplaintRefId
    });

    if (fallbackSubject) {
        fallbackSubject.value = complaint.subject;
        fallbackSubject.innerText = complaint.subject;
    }
    if (fallbackBody) {
        fallbackBody.value = complaint.body;
        fallbackBody.innerText = complaint.body;
    }
    if (fallbackTo) {
        fallbackTo.value = complaint.to;
        fallbackTo.innerText = complaint.to;
    }

    return complaint;
}

function openComplaintModal() {
    if (!currentLocation) {
        currentLocation = {
            name: "CGS Colony",
            locality: "CGS Colony, Ghatkopar",
            city: "Mumbai",
            state: "Maharashtra",
            latitude: 19.0860,
            longitude: 72.9090
        };
    }

    // Pre-fill default complainant name & description if empty so user can send immediately
    if (complaintUserName && !complaintUserName.value) {
        complaintUserName.value = "Concerned Citizen";
    }
    if (complaintDescInput && !complaintDescInput.value) {
        complaintDescInput.value = "Severe smoke, dust, and particulate matter observed in the vicinity. Air quality is notably deteriorated, causing visible haze and breathing discomfort. Requesting immediate environmental inspection and regulatory action under the Air (Prevention and Control of Pollution) Act.";
    }
    if (charCountLabel && complaintDescInput) {
        charCountLabel.innerText = `${complaintDescInput.value.length} / 3000`;
    }

    // Reset Form & Views
    if (complaintModalBody) complaintModalBody.style.display = "block";
    if (complaintModalFooter) complaintModalFooter.style.display = "flex";
    if (modalSuccessView) modalSuccessView.style.display = "none";
    if (modalStatusBanner) modalStatusBanner.style.display = "none";
    if (fallbackNoticeBox) fallbackNoticeBox.style.display = "none";

    // Initialize fresh reference ID for this complaint session
    currentComplaintRefId = generateProvisionalRefId();
    if (modalRefIdDisplay) modalRefIdDisplay.innerText = currentComplaintRefId;
    if (refStorageLabel) {
        refStorageLabel.innerText = "(Draft in local session)";
        refStorageLabel.style.color = "#93c5fd";
    }
    if (civicStatusText) {
        civicStatusText.innerText = "Complaint email ready for review";
    }

    if (submitComplaintBtn) {
        submitComplaintBtn.disabled = false;
        if (submitComplaintBtnText) submitComplaintBtnText.innerText = "Send Mail / Open Email App";
    }
    if (openGmailBtn) {
        openGmailBtn.removeAttribute("disabled");
    }
    if (testEmailBtn) {
        testEmailBtn.disabled = false;
        if (testEmailBtnText) testEmailBtnText.innerText = "Send Test to Me";
    }

    // Pre-fill / review location (reusing detected or manual location)
    const locName = currentLocation.name || currentLocation.locality || currentLocation.city || "Reported Location";
    if (complaintLocationInput) complaintLocationInput.value = locName;
    if (modalLocDetails) {
        modalLocDetails.innerHTML = `<i class="fa-solid fa-map-pin"></i> ${escapeHtml(currentLocation.display_name || `${locName}, India`)}`;
    }

    // Ensure authorities dropdown is loaded
    loadAuthoritiesDirectory();

    // Pre-fill authority from verified backend directory
    if (currentAuthorityData) {
        syncAuthorityUi(currentAuthorityData);
    } else {
        if (authorityVerifyBadge) {
            authorityVerifyBadge.innerText = "Unverified / Missing";
            authorityVerifyBadge.style.background = "#fee2e2";
            authorityVerifyBadge.style.color = "#b91c1c";
        }
        if (authorityVerifyWarning) {
            authorityVerifyWarning.style.display = "flex";
        }
    }

    // Pre-fill live atmospheric readings when available (graceful when empty - never fabricate)
    const hasAqi = Boolean(currentAqiData && currentAqiData.aqi !== undefined && currentAqiData.aqi !== null && currentAqiData.aqi !== "--");
    if (hasAqi) {
        if (modalAqiStrip) modalAqiStrip.style.display = "flex";
        if (noAqiNotice) noAqiNotice.style.display = "none";
        if (aqiAvailabilityTag) aqiAvailabilityTag.innerText = "Verified sensor data";

        const aqiVal = currentAqiData.aqi;
        const cat = currentAqiData.category || getCategoryName(aqiVal);
        const col = getCategoryColor(aqiVal, cat);

        if (modalAqiNum) modalAqiNum.innerText = aqiVal;
        if (modalAqiCat) modalAqiCat.innerText = cat;
        if (modalAqiBadge) modalAqiBadge.style.backgroundColor = col;

        if (modalPm25) modalPm25.innerText = (currentAqiData.pm25 !== undefined && currentAqiData.pm25 !== null) ? `${currentAqiData.pm25} µg/m³` : "--";
        if (modalPm10) modalPm10.innerText = (currentAqiData.pm10 !== undefined && currentAqiData.pm10 !== null) ? `${currentAqiData.pm10} µg/m³` : "--";

        const now = new Date();
        if (modalTimestamp) modalTimestamp.innerText = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else {
        if (modalAqiStrip) modalAqiStrip.style.display = "none";
        if (noAqiNotice) noAqiNotice.style.display = "flex";
        if (aqiAvailabilityTag) aqiAvailabilityTag.innerText = "No sensor data";
    }

    // Reset photo
    clearPhotoPreview();

    // Update live draft preview
    updateDraftPreview();

    // Show modal
    if (complaintModalOverlay) {
        complaintModalOverlay.classList.add("show");
        complaintModalOverlay.setAttribute("aria-hidden", "false");
    }

    if (complaintUserName && !complaintUserName.value) {
        complaintUserName.focus();
    } else if (complaintLocationInput) {
        complaintLocationInput.focus();
    }
}

function closeComplaintModal() {
    if (complaintModalOverlay) {
        complaintModalOverlay.classList.remove("show");
        complaintModalOverlay.setAttribute("aria-hidden", "true");
    }
}

openComplaintModalBtn?.addEventListener("click", openComplaintModal);
closeComplaintModalBtn?.addEventListener("click", closeComplaintModal);
cancelComplaintBtn?.addEventListener("click", closeComplaintModal);
closeSuccessModalBtn?.addEventListener("click", closeComplaintModal);

// Close on backdrop click
complaintModalOverlay?.addEventListener("click", (e) => {
    if (e.target === complaintModalOverlay) {
        closeComplaintModal();
    }
});

// Close on Escape key
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && complaintModalOverlay.classList.contains("show")) {
        closeComplaintModal();
    }
});

// Authority Selector Change Handler
authoritySelector?.addEventListener("change", () => {
    const selectedId = authoritySelector.value;
    if (!selectedId) {
        if (currentAuthorityData) syncAuthorityUi(currentAuthorityData);
        updateDraftPreview();
        return;
    }
    const match = cachedAuthoritiesList.find(a => a.id === selectedId);
    if (match) {
        currentAuthorityData = match;
        syncAuthorityUi(match);
        updateDraftPreview();
    }
});

// Live update of draft preview on inputs
[complaintUserName, complaintUserEmail, complaintLocationInput, complaintRecipientEmail, complaintSourceSelect, complaintDescInput].forEach(el => {
    el?.addEventListener("input", updateDraftPreview);
});

// Character Counter
complaintDescInput?.addEventListener("input", () => {
    const len = complaintDescInput.value.length;
    if (charCountLabel) {
        charCountLabel.innerText = `${len} / 3000`;
        if (len > 3000) {
            charCountLabel.style.color = "#dc2626";
        } else {
            charCountLabel.style.color = "#64748b";
        }
    }
    updateDraftPreview();
});

// Quick Insert Chips (supports both .civic-chip and .desc-chip)
document.querySelectorAll(".civic-chip, .desc-chip").forEach(chip => {
    chip.addEventListener("click", () => {
        const text = chip.getAttribute("data-text");
        if (text) {
            const current = complaintDescInput.value.trim();
            complaintDescInput.value = current ? `${current} ${text}` : text;
            complaintDescInput.dispatchEvent(new Event("input"));
            complaintDescInput.focus();
        }
    });
});

// Photo Upload Handling
uploadDropZone?.addEventListener("click", (e) => {
    if (e.target.closest("#removePhotoBtn")) return;
    complaintPhotoInput?.click();
});

complaintPhotoInput?.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) handlePhotoFile(file);
});

uploadDropZone?.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadDropZone.style.borderColor = "#1e3a8a";
});

uploadDropZone?.addEventListener("dragleave", () => {
    uploadDropZone.style.borderColor = "";
});

uploadDropZone?.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadDropZone.style.borderColor = "";
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handlePhotoFile(e.dataTransfer.files[0]);
    }
});

function handlePhotoFile(file) {
    if (!file.type.startsWith("image/")) {
        alert("Please upload an image file (JPG, PNG, or WEBP).");
        return;
    }
    if (file.size > 5 * 1024 * 1024) {
        alert("Photo evidence must be smaller than 5MB.");
        return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
        selectedPhotoBase64 = event.target.result;
        photoPreviewImg.src = selectedPhotoBase64;
        photoPreviewName.innerText = file.name;
        uploadPrompt.style.display = "none";
        photoPreviewWrap.style.display = "flex";
    };
    reader.readAsDataURL(file);
}

function clearPhotoPreview() {
    selectedPhotoBase64 = null;
    if (complaintPhotoInput) complaintPhotoInput.value = "";
    if (uploadPrompt) uploadPrompt.style.display = "flex";
    if (photoPreviewWrap) photoPreviewWrap.style.display = "none";
}

removePhotoBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    clearPhotoPreview();
});

// ── Mailto Link & Professional Complaint Body Builder ───────────
function generateMailtoUrl({ to, subject, body }) {
    const cleanTo = (to || "").trim();
    // RFC 6068: In the addr-spec portion before '?', preserve '@' for universal mail client compatibility
    const encodedTo = encodeURIComponent(cleanTo).replace(/%40/g, "@");
    const encodedSubject = encodeURIComponent(subject || "");
    const encodedBody = encodeURIComponent(body || "");
    return `mailto:${encodedTo}?subject=${encodedSubject}&body=${encodedBody}`;
}

function buildComplaintContent({
    name,
    email = "",
    locationName,
    locationData = null,
    recipientEmail,
    source = "General",
    description,
    aqiData = null,
    weatherData = null,
    authorityData = null,
    refId = ""
}) {
    const cleanName = (name || "").trim();
    const cleanEmail = (email || "").trim();
    const cleanLoc = (locationName || "").trim();
    const cleanDesc = (description || "").trim();
    const authName = authorityData?.authority_name || "Environmental Regulatory Authority";
    const jurisdiction = authorityData?.jurisdiction_scope || cleanLoc;

    const subject = `Air Pollution Complaint - ${cleanLoc}`;

    let body = `TO: ${authName}\n`;
    body += `JURISDICTION: ${jurisdiction}\n\n`;
    body += `OFFICIAL CITIZEN AIR POLLUTION COMPLAINT\n`;
    if (refId) {
        body += `Tracking Reference: ${refId}\n`;
    }
    body += `Platform: SkyCheck Citizen Environmental Monitoring Platform\n`;
    body += `Date: ${new Date().toLocaleDateString("en-IN", { year: "numeric", month: "long", day: "numeric" })}\n`;
    body += `======================================================================\n\n`;

    body += `1. CITIZEN COMPLAINANT:\n`;
    body += `Name          : ${cleanName}\n`;
    body += `Contact Email : ${cleanEmail || "Not provided (Anonymous submission)"}\n\n`;

    body += `2. INCIDENT LOCATION:\n`;
    body += `Location / Landmark : ${cleanLoc}\n`;
    const ward = locationData?.ward || authorityData?.ward_code;
    if (ward) body += `Ward / Zone         : ${ward}\n`;
    if (locationData?.city) body += `City                : ${locationData.city}\n`;
    if (locationData?.district) body += `District            : ${locationData.district}\n`;
    if (locationData?.state) body += `State               : ${locationData.state}\n`;
    if (locationData?.latitude && locationData?.longitude) {
        body += `GPS Coordinates     : ${locationData.latitude}, ${locationData.longitude}\n`;
    }
    body += `\n`;

    body += `3. POLLUTION OBSERVATION & CITIZEN STATEMENT:\n`;
    body += `Observed Issue Type : ${source}\n`;
    body += `Incident Statement  :\n${cleanDesc}\n\n`;

    body += `4. ATMOSPHERIC OBSERVATIONS AT TIME OF COMPLAINT:\n`;
    const hasAqi = Boolean(aqiData && aqiData.aqi !== undefined && aqiData.aqi !== null && aqiData.aqi !== "--");
    if (hasAqi) {
        const cat = aqiData.category || getCategoryName(aqiData.aqi);
        body += `Indian NAQI (CPCB) : ${aqiData.aqi} - ${cat}\n`;
        if (aqiData.pm25 !== undefined && aqiData.pm25 !== null) body += `PM2.5 (Fine Dust)  : ${aqiData.pm25} µg/m³\n`;
        if (aqiData.pm10 !== undefined && aqiData.pm10 !== null) body += `PM10 (Coarse Dust) : ${aqiData.pm10} µg/m³\n`;
        if (aqiData.no2 !== undefined && aqiData.no2 !== null) body += `NO2                : ${aqiData.no2} µg/m³\n`;
        if (aqiData.so2 !== undefined && aqiData.so2 !== null) body += `SO2                : ${aqiData.so2} µg/m³\n`;
        if (aqiData.co !== undefined && aqiData.co !== null) body += `CO                 : ${aqiData.co} mg/m³\n`;
        if (aqiData.o3 !== undefined && aqiData.o3 !== null) body += `Ozone (O3)         : ${aqiData.o3} µg/m³\n`;
        if (weatherData && weatherData.temperature !== undefined) {
            body += `Weather Conditions : Temp ${weatherData.temperature}°C | Humidity ${weatherData.humidity || 'N/A'}% | Wind ${weatherData.wind || 'N/A'} m/s\n`;
        }
    } else {
        body += `Sensor readings    : Sensor observations not recorded for this specific coordinate at time of complaint.\n`;
    }
    body += `\n`;

    body += `5. FORMAL REQUEST FOR INSPECTION & REGULATORY ACTION:\n`;
    body += `I respectfully request the competent environmental and municipal authorities to inspect the reported site, investigate this emission source, and initiate appropriate regulatory and remedial measures under the Air (Prevention and Control of Pollution) Act, 1981 and relevant municipal environmental guidelines.\n\n`;
    if (cleanEmail) {
        body += `Please provide inspection updates and acknowledgment to the contact email specified above.\n\n`;
    }
    body += `Respectfully submitted,\n${cleanName}\n`;

    const mailtoUrl = generateMailtoUrl({ to: recipientEmail, subject, body });

    return {
        to: recipientEmail,
        subject,
        body,
        mailtoUrl
    };
}

// Expose on window for automated headless test verification
window.generateMailtoUrl = generateMailtoUrl;
window.buildComplaintContent = buildComplaintContent;

// 1-Click Copy with Visual Feedback
function copyWithFeedback(btn, textToCopy, originalHtml) {
    if (!textToCopy) return;
    const doFeedback = () => {
        btn.innerHTML = '<i class="fa-solid fa-check"></i> Copied!';
        setTimeout(() => {
            btn.innerHTML = originalHtml;
        }, 2000);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(textToCopy).then(doFeedback).catch(doFeedback);
    } else {
        const el = document.createElement("textarea");
        el.value = textToCopy;
        document.body.appendChild(el);
        el.select();
        document.execCommand("copy");
        document.body.removeChild(el);
        doFeedback();
    }
}

// Hook up copy buttons
copyRefIdBtn?.addEventListener("click", () => {
    const ref = (modalRefIdDisplay?.innerText || currentComplaintRefId).trim();
    copyWithFeedback(copyRefIdBtn, ref, '<i class="fa-solid fa-copy"></i> Copy Reference ID');
});
const handleCopyTo = (btn) => {
    const to = complaintRecipientEmail?.value || fallbackTo?.innerText || fallbackTo?.value || "";
    copyWithFeedback(btn, to, '<i class="fa-solid fa-copy"></i> Copy');
};
copyToBtn?.addEventListener("click", () => handleCopyTo(copyToBtn));
document.getElementById("copyToBtnModal")?.addEventListener("click", function() { handleCopyTo(this); });

copySubjectBtn?.addEventListener("click", () => {
    const sub = fallbackSubject?.innerText || fallbackSubject?.value || "";
    copyWithFeedback(copySubjectBtn, sub, '<i class="fa-solid fa-copy"></i> Copy');
});
copyBodyBtn?.addEventListener("click", () => {
    const body = fallbackBody?.value || fallbackBody?.innerText || "";
    copyWithFeedback(copyBodyBtn, body, '<i class="fa-solid fa-copy"></i> Copy Body');
});

// Copy all details
copyAllDetailsBtn?.addEventListener("click", () => {
    const to = complaintRecipientEmail?.value || fallbackTo?.innerText || fallbackTo?.value || "";
    const sub = fallbackSubject?.innerText || fallbackSubject?.value || "";
    const body = fallbackBody?.value || fallbackBody?.innerText || "";
    const allText = `TO: ${to}\nSUBJECT: ${sub}\n\n${body}`;
    copyWithFeedback(copyAllDetailsBtn, allText, '<i class="fa-solid fa-copy"></i> <span>Copy Complaint Details</span>');
});

// Back to Edit Complaint Handler (compatibility)
backToEditBtn?.addEventListener("click", () => {
    if (modalSuccessView) modalSuccessView.style.display = "none";
    if (complaintModalBody) complaintModalBody.style.display = "block";
    if (complaintModalFooter) complaintModalFooter.style.display = "flex";
    if (modalStatusBanner) modalStatusBanner.style.display = "none";
});

// Asynchronous backend audit logging (fire-and-forget in background without delaying user click action)
function recordDraftAuditAsync(payload) {
    fetch(`${API_BASE}/api/complaints/record-draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    }).then(r => r.json()).then(data => {
        if (data.success && data.ref_id) {
            currentComplaintRefId = data.ref_id;
            if (modalRefIdDisplay) modalRefIdDisplay.innerText = data.ref_id;
            if (refStorageLabel) {
                refStorageLabel.innerText = "(Recorded in civic database)";
                refStorageLabel.style.color = "#166534";
            }
        }
    }).catch(err => {
        console.warn("Background draft audit logging notice:", err);
    });
}

// Validation helper
function validateComplaintForm() {
    const name = (complaintUserName.value || "").trim();
    if (!name) {
        return { valid: false, message: "Please enter your full name as the official citizen complainant.", field: complaintUserName };
    }

    const email = (complaintUserEmail.value || "").trim();
    const emailRegex = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
    if (email && !emailRegex.test(email)) {
        return { valid: false, message: "Please enter a valid contact email address or leave it blank.", field: complaintUserEmail };
    }

    const locInput = (complaintLocationInput.value || "").trim();
    if (!locInput) {
        return { valid: false, message: "Please provide the incident location or landmark.", field: complaintLocationInput };
    }

    const recipient = (complaintRecipientEmail.value || "").trim();
    if (!recipient || !emailRegex.test(recipient)) {
        return { valid: false, message: "Official recipient authority email is missing or unverified. Please select a verified authority from the dropdown above or enter an official government email address.", field: complaintRecipientEmail };
    }

    const desc = (complaintDescInput.value || "").trim();
    if (desc.length < 10) {
        return { valid: false, message: "Please describe the pollution condition in at least 10 characters.", field: complaintDescInput };
    }
    if (desc.length > 3000) {
        return { valid: false, message: "Complaint description exceeds the maximum length of 3,000 characters.", field: complaintDescInput };
    }

    return { valid: true };
}

// ── Action 1: Open Email App (Default mailto: client) ──────────────
// Triggers directly on user click without any async delay to prevent browser popup blockers!
submitComplaintBtn?.addEventListener("click", () => {
    modalStatusBanner.style.display = "none";

    // Auto-fill defaults if empty so user is never silently blocked
    if (!complaintUserName.value.trim()) {
        complaintUserName.value = "Concerned Citizen";
    }
    if (!complaintDescInput.value.trim()) {
        complaintDescInput.value = "Severe smoke, dust, and particulate matter observed in the vicinity. Air quality is notably deteriorated, causing visible haze and breathing discomfort. Requesting immediate environmental inspection and regulatory action under the Air (Prevention and Control of Pollution) Act.";
    }
    if (!complaintRecipientEmail.value.trim()) {
        complaintRecipientEmail.value = currentAuthorityData?.email || "ac.fn@mcgm.gov.in";
    }

    const val = validateComplaintForm();
    if (!val.valid) {
        showModalStatus(val.message, "error");
        val.field?.focus();
        return;
    }

    // Refresh draft content
    const complaint = updateDraftPreview();

    // Trigger mailto: directly and synchronously via window.location.href
    try {
        window.location.href = complaint.mailtoUrl;
    } catch (launchErr) {
        console.warn("Mail application launch invocation:", launchErr);
        const mailLink = document.createElement("a");
        mailLink.href = complaint.mailtoUrl;
        document.body.appendChild(mailLink);
        mailLink.click();
        setTimeout(() => { try { mailLink.remove(); } catch { } }, 500);
    }

    // Show civic confirmation & fallback instructions
    if (civicStatusText) civicStatusText.innerText = "Email composer requested";
    showModalStatus(
        `<strong>Email composer requested.</strong> Please check your email application to review the prefilled draft and press <strong>Send</strong>.<br>` +
        `<span style="font-size: 11.5px; opacity: 0.95;">If your email application did not open, click <strong>Open Gmail</strong> or use the <strong>Copy Complaint Details</strong> button below.</span>`,
        "success"
    );

    if (fallbackNoticeBox) {
        fallbackNoticeBox.style.display = "flex";
    }

    // Persist draft audit in background without blocking user navigation
    recordDraftAuditAsync({
        ref_id: currentComplaintRefId,
        user_name: complaintUserName.value.trim(),
        user_email: complaintUserEmail.value.trim(),
        location: {
            name: complaintLocationInput.value.trim(),
            locality: currentLocation?.locality,
            ward: currentLocation?.ward || currentAuthorityData?.ward_code,
            city: currentLocation?.city,
            district: currentLocation?.district,
            state: currentLocation?.state,
            latitude: currentLocation?.latitude,
            longitude: currentLocation?.longitude,
        },
        location_name: complaintLocationInput.value.trim(),
        air_quality: currentAqiData,
        weather: currentWeatherData,
        pollution_source: complaintSourceSelect.value,
        description: complaintDescInput.value.trim(),
        authority_name: currentAuthorityData?.authority_name || "Environmental Authority",
        recipient_email: complaintRecipientEmail.value.trim(),
        photo_evidence: Boolean(selectedPhotoBase64)
    });
});

// ── Action 2: Open Gmail (Webmail compose tab) ───────────────────
// Triggers directly on user click without any async delay to avoid popup blocker!
openGmailBtn?.addEventListener("click", (e) => {
    e.preventDefault();
    modalStatusBanner.style.display = "none";

    const val = validateComplaintForm();
    if (!val.valid) {
        showModalStatus(val.message, "error");
        val.field?.focus();
        return;
    }

    // Refresh draft content
    const complaint = updateDraftPreview();

    const encTo = encodeURIComponent(complaint.to);
    const encSub = encodeURIComponent(complaint.subject);
    const encBody = encodeURIComponent(complaint.body);
    const gmailUrl = `https://mail.google.com/mail/?view=cm&fs=1&to=${encTo}&su=${encSub}&body=${encBody}`;

    // Open synchronously inside click handler so modern browsers never block the popup
    const newTab = window.open(gmailUrl, "_blank", "noopener,noreferrer");
    if (!newTab || newTab.closed || typeof newTab.closed === "undefined") {
        // Fallback if browser blocked window.open
        window.location.href = gmailUrl;
    }

    if (civicStatusText) civicStatusText.innerText = "Gmail draft opened in new tab";
    showModalStatus(
        `<strong>Gmail compose opened.</strong> Review your prefilled draft in Gmail and press <strong>Send</strong>.<br>` +
        `<span style="font-size: 11.5px; opacity: 0.95;">Note: Please ensure you are signed in to your Google account. Your draft has not been sent yet.</span>`,
        "success"
    );

    // Persist draft audit in background without blocking
    recordDraftAuditAsync({
        ref_id: currentComplaintRefId,
        user_name: complaintUserName.value.trim(),
        user_email: complaintUserEmail.value.trim(),
        location: {
            name: complaintLocationInput.value.trim(),
            locality: currentLocation?.locality,
            ward: currentLocation?.ward || currentAuthorityData?.ward_code,
            city: currentLocation?.city,
            district: currentLocation?.district,
            state: currentLocation?.state,
            latitude: currentLocation?.latitude,
            longitude: currentLocation?.longitude,
        },
        location_name: complaintLocationInput.value.trim(),
        air_quality: currentAqiData,
        weather: currentWeatherData,
        pollution_source: complaintSourceSelect.value,
        description: complaintDescInput.value.trim(),
        authority_name: currentAuthorityData?.authority_name || "Environmental Authority",
        recipient_email: complaintRecipientEmail.value.trim(),
        photo_evidence: Boolean(selectedPhotoBase64)
    });
});

// Safe Diagnostic Email Test Action (SMTP-based, kept strictly separate)
if (testEmailBtn) {
    testEmailBtn.addEventListener("click", async () => {
        if (isSubmittingComplaint) return;

        modalStatusBanner.style.display = "none";

        const email = complaintUserEmail.value.trim();
        const emailRegex = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
        if (!email || !emailRegex.test(email)) {
            showModalStatus("Please enter your email address in the contact email field above to receive the safe test message.", "error");
            complaintUserEmail.focus();
            return;
        }

        // Set loading state
        testEmailBtn.disabled = true;
        submitComplaintBtn.disabled = true;
        testEmailBtnText.innerText = "Sending Test...";
        showModalStatus('<i class="fa-solid fa-spinner fa-spin"></i> Connecting to SMTP server to verify route to ' + escapeHtml(email) + '...', "loading");

        try {
            const resp = await fetch(`${API_BASE}/api/email/test`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ user_email: email })
            });

            const resData = await resp.json();

            if (resp.ok && resData.success) {
                showModalStatus(
                    `<strong>Safe Test Email Accepted by SMTP Server!</strong><br>` +
                    `A diagnostic test message was successfully accepted for delivery to <strong>${escapeHtml(email)}</strong>.<br>` +
                    `<span style="font-size:12px; opacity:0.9; margin-top:4px; display:inline-block;">` +
                    `<em>Delivery Notice:</em> SMTP acceptance confirms the mail server accepted the transmission. Delivery to your Inbox or Spam folder depends on your provider's spam filters and MX routing.</span>`,
                    "success"
                );
            } else {
                const errMsg = resData.message || "Failed to send test email.";
                let safeGuide = "";
                if (resData.error_code === "SMTP_NOT_CONFIGURED") {
                    safeGuide = `<br><span style="font-size:12px; margin-top:4px; display:inline-block; color:#fecaca;">` +
                        `To enable real email sending, configure <code>SMTP_HOST</code>, <code>SMTP_PORT</code>, <code>SMTP_USERNAME</code>, and <code>SMTP_PASSWORD</code> in <code>.env</code>.</span>`;
                }
                showModalStatus(`<strong>SMTP Test Result:</strong> ${escapeHtml(errMsg)}${safeGuide}`, "error");
            }
        } catch (err) {
            console.error("Test email transmission error:", err);
            showModalStatus("Network connection error. Please ensure the backend server is running and retry.", "error");
        } finally {
            testEmailBtn.disabled = false;
            submitComplaintBtn.disabled = false;
            testEmailBtnText.innerText = "Send Test to Me";
        }
    });
}

function showModalStatus(htmlMsg, type) {
    if (!modalStatusBanner) return;
    modalStatusBanner.className = `modal-status-banner ${type}`;
    modalStatusBanner.innerHTML = htmlMsg;
    modalStatusBanner.style.display = "block";
}


// ── 9. Drawer Navigation Menu ───────────────────────────────────
function openDrawer() {
    sideMenu.classList.add("open");
    drawerBackdrop.classList.add("show");
    sideMenu.setAttribute("aria-hidden", "false");
}

function closeDrawer() {
    sideMenu.classList.remove("open");
    drawerBackdrop.classList.remove("show");
    sideMenu.setAttribute("aria-hidden", "true");
}

menuToggleBtn.addEventListener("click", openDrawer);
closeMenuBtn.addEventListener("click", closeDrawer);
drawerBackdrop.addEventListener("click", () => {
    closeDrawer();
    closeSearchOverlay();
});

document.getElementById("menuSearchBtn")?.addEventListener("click", () => {
    closeDrawer();
    openSearchOverlay();
});

document.getElementById("menuHistoryBtn")?.addEventListener("click", () => {
    closeDrawer();
    document.getElementById("historySectionCard")?.scrollIntoView({ behavior: "smooth" });
});

document.getElementById("menuPollutantsBtn")?.addEventListener("click", () => {
    closeDrawer();
    document.getElementById("pollutantsCard")?.scrollIntoView({ behavior: "smooth" });
});

document.getElementById("menuAdvisoryBtn")?.addEventListener("click", () => {
    closeDrawer();
    document.getElementById("advisoryCard")?.scrollIntoView({ behavior: "smooth" });
});

document.getElementById("menuAuthorityBtn")?.addEventListener("click", () => {
    closeDrawer();
    openComplaintModal();
});

document.getElementById("menuRefreshBtn")?.addEventListener("click", () => {
    closeDrawer();
    refreshDashboard();
});

headerRefreshBtn?.addEventListener("click", () => {
    refreshDashboard();
});

// GPS / Current Location Triggers
headerLocationBtn?.addEventListener("click", () => {
    requestUserLocation();
});

useCurrentLocationBtn?.addEventListener("click", () => {
    closeSearchOverlay();
    requestUserLocation();
});

menuLocationBtn?.addEventListener("click", () => {
    closeDrawer();
    requestUserLocation();
});


// ── 10. Search Triggers & Event Listeners ────────────────────────
searchToggleBtn?.addEventListener("click", () => {
    if (searchBarOverlay.classList.contains("show")) {
        closeSearchOverlay();
    } else {
        openSearchOverlay();
    }
});

locationTitleBtn?.addEventListener("click", () => {
    openSearchOverlay();
});

// Debounced input search for responsive location suggestions (280ms)
cityInput?.addEventListener("input", () => {
    const q = cityInput.value.trim();
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);

    if (q.length === 0) {
        closeLocationDropdown();
        return;
    }

    searchDebounceTimer = setTimeout(() => {
        handleSearchInput(q);
    }, 280);
});

// Enter key triggers immediate search & selection
cityInput?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
        const q = cityInput.value.trim();
        if (q) {
            userHasSelectedManualLocation = true;
            searchLocation(q, true);
        }
    }
});

clearSearchBtn?.addEventListener("click", () => {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    if (searchAbortController) searchAbortController.abort();
    cityInput.value = "";
    closeLocationDropdown();
    cityInput.focus();
});

// Popular quick pills
document.querySelectorAll(".quick-pill").forEach(pill => {
    pill.addEventListener("click", () => {
        const loc = pill.getAttribute("data-loc");
        if (loc) {
            userHasSelectedManualLocation = true;
            cityInput.value = loc;
            searchLocation(loc, true);
        }
    });
});

// Auto-Refresh
function startAutoRefresh(loc) {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }
    autoRefreshTimer = setInterval(() => {
        if (currentLocation) {
            loadDashboardForLocation(currentLocation, true);
        }
    }, REFRESH_INTERVAL_MS);
}

// Clean up background timers on page unload
window.addEventListener("beforeunload", () => {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
    }
    if (dashboardAbortController) {
        dashboardAbortController.abort();
    }
    if (searchAbortController) {
        searchAbortController.abort();
    }
});


// ── 11. Initial Application Boot: Automatic Startup Live Location ─────────
let startupLocationInitiated = false;

document.addEventListener("DOMContentLoaded", () => {
    if (startupLocationInitiated) return;
    startupLocationInitiated = true;

    // Preload verified authorities directory for complaint form
    loadAuthoritiesDirectory();

    // Additional Requirement: Automatically detect user's live location without requiring a button click
    if ("geolocation" in navigator) {
        if (navigator.permissions && navigator.permissions.query) {
            navigator.permissions.query({ name: "geolocation" }).then((perm) => {
                if (perm.state === "granted") {
                    // Permission already granted: detect immediately without asking again
                    requestUserLocation(true);
                } else if (perm.state === "prompt") {
                    // Trigger browser's native permission prompt with clear informative notice
                    requestUserLocation(true);
                } else {
                    // Permission denied: show clear explanation and fall back to default location
                    showLocationNotice("Location access is denied. Showing default area. You can search for any city or ward above.", "info", 5000);
                    searchLocation("CGS Colony", true);
                }

                // If user changes permission in browser settings, react gracefully
                perm.onchange = () => {
                    if (perm.state === "granted" && !userHasSelectedManualLocation) {
                        requestUserLocation(true);
                    }
                };
            }).catch(() => {
                requestUserLocation(true);
            });
        } else {
            // Browser doesn't support permissions API: trigger native geolocation prompt
            requestUserLocation(true);
        }
    } else {
        // Geolocation not supported: fallback smoothly
        searchLocation("CGS Colony", true);
    }
});