# SkyCheck / AirGuard AI – Advanced AQI Analytics & Environmental Grievance System

SkyCheck is a full-stack real-time air quality monitoring and citizen environmental grievance application built with Python Flask, SQLite, HTML5, Vanilla CSS3 (Glassmorphism), Chart.js, and JavaScript.

---

## What's New in this Upgrade

### Feature A: Premium Historical AQI & Pollutant Analytics Dashboard
- **Interactive Multi-Day Time-Series Chart:** Dynamic Chart.js visualization with smooth bezier curves (`tension: 0.36`), translucent gradient area shading, hover tooltips, responsive gridlines, and CPCB AQI severity bands.
- **Flexible Time Ranges:** 7-Day, 14-Day, and 30-Day time-series views with real atmospheric data and coverage indicators.
- **Metric Comparison Modes:** Toggle between **AQI Trend**, **PM2.5**, **PM10**, and **Compare All** (multi-line comparative overlay).
- **Summary Analytics:** Period Average AQI, Peak/Max, Lowest/Min, Best Day, Worst Day, Percentage Change, and trend direction indicators (▲ Worsening / ▼ Improving / ● Stable).
- **Narrative Trend Analysis:** Human-readable atmospheric analysis summarizing percentage changes and dominant pollutants.
- **Daily Breakdown Strip:** Detailed daily breakdown cards with date, AQI badges, category pills, and particulate metrics.
- **Pollutant Breakdown Cards:** Real-time sensor metrics for PM2.5, PM10, NO₂, SO₂, CO (with `mg/m³`), O₃, and NH₃ with dynamic risk severity badges (*Normal*, *Moderate*, *High*, *Hazardous*).
- **Zero Data Fabrication:** Uses real atmospheric observation & reanalysis data from Open-Meteo and Google Air Quality, with persistent daily SQLite snapshot storage (`aqi_history`). Periods with incomplete history are explicitly labeled.

### Feature B: Location-Aware Government Pollution Complaint Email System
- **Prominent Citizen Grievance Portal:** One-click modal on the dashboard for reporting pollution violations to verified government bodies.
- **Hierarchical Jurisdiction Resolution:**
  - **Local Wards:** Automatically maps Mumbai localities (e.g., CGS Colony, Antop Hill, Wadala, Matunga, Sion) to **BMC Ward F/North Office** (`ac.fn@mcgm.gov.in`), Ward A (`ac.a@mcgm.gov.in`), Ward F/South, Ward G/South, Ward H/West, Ward K/West, Ward K/East, etc.
  - **Municipal Fallback:** Unmapped Mumbai areas are routed to **BMC Central Environment & Disaster Control Cell** (`dmc.env@mcgm.gov.in`) with an explicit fallback explanation.
  - **State Pollution Control Boards:** Automatic routing to State PCBs (MPCB for Maharashtra, DPCC for Delhi-NCR, KSPCB for Karnataka, TNPCB for Tamil Nadu, TGSPCB for Telangana, WBPCB for West Bengal, GPCB for Gujarat, UPPCB for Uttar Pradesh).
  - **National Fallback:** Central Pollution Control Board (CPCB `cpcb@nic.in`) and the official national **SAMEER App / Grievance Portal** (`https://sameer.cpcb.gov.in`).
- **Verified Authority Directory:** Directory in `backend/data/authority_mapping.json` storing official contact emails, escalation offices, source URLs (`portal.mcgm.gov.in`, `mpcb.gov.in`, `cpcb.nic.in`), verification dates (March 2026), and active status.
- **Citizen Complainant Form:**
  - Citizen email input (validated, set as `Reply-To` so authorities reply directly to the citizen).
  - Pre-filled location & live atmospheric measurements (AQI, PM2.5, PM10, timestamp).
  - Observed pollution source selector (Construction Dust, Waste Burning, Industrial Smoke, Vehicular Traffic, etc.).
  - Detailed complaint description with live character counter (0 / 3000) and quick-insert statement chips.
  - Optional photo evidence upload (JPG, PNG, WEBP, max 5MB) with image preview.
  - Citizen privacy notice and consent authorization checkbox.
- **Robust Security & Anti-Abuse:**
  - Server-side email header injection sanitization (strips `\r` and `\n` from headers).
  - Anti-duplicate submission protection (rejects identical reports within 5 minutes).
  - In-memory rate limiting (max 3 complaints per 10 minutes per IP/email).
  - Trusted backend routing: the browser client cannot override the recipient email; the recipient is resolved from the verified server-side directory.
- **Dual Delivery Engine:**
  - **Live Production Mode:** Dispatches multipart plain-text + responsive HTML emails via SMTP (Gmail, SendGrid, Amazon SES, Brevo, etc.) with attached photo evidence.
  - **Development Test Mode (Mock Gateway):** Runs out-of-the-box when SMTP is not configured. Validates MIME structure, logs full audit trails in SQLite (`complaints` table), and returns a unique Reference ID (`SKY-TEST-2026-XXXX`).
- **Audit & Persistence:** Stores complaint records in SQLite with masked email (`u***@domain.com`) for citizen privacy compliance.

---

## Tech Stack

- **Frontend:** HTML5, Vanilla CSS3 (Glassmorphism), Vanilla JavaScript (ES6+), Chart.js v4, Font Awesome 6.
- **Backend:** Python 3, Flask, Flask-CORS, Requests, SQLite3, `smtplib`.
- **Database:** SQLite (`database/airguard.db`) with tables:
  - `complaints`: Citizen complaint audit trail, reference IDs, and send statuses.
  - `authorities`: Verified municipal and environmental authority directory.
  - `aqi_history`: Persisted daily atmospheric readings.
  - `locations`: Geocoded location cache.
  - `search_history`: Search query logs.

---

## Directory Structure

```
SkyCheck/
├── backend/
│   ├── app.py                      # Flask API server & endpoints
│   ├── config.py                   # Environment variable loader
│   ├── database.py                 # SQLite schema, migrations & CRUD helpers
│   ├── requirements.txt            # Python dependencies
│   ├── services/
│   │   ├── __init__.py
│   │   ├── authority_service.py    # Location-aware authority resolution
│   │   ├── email_service.py        # SMTP email dispatch & anti-abuse engine
│   │   ├── history_service.py      # Multi-day atmospheric analytics & trends
│   │   ├── air_quality_service.py  # Google & Open-Meteo real-time AQI
│   │   ├── geocoding_service.py    # Open-Meteo & Nominatim geocoding
│   │   └── weather_service.py      # Open-Meteo Weather service
│   └── data/
│       └── authority_mapping.json  # Verified government authority directory
├── frontend/
│   ├── index.html                  # Advanced analytics UI & complaint modal
│   ├── app.css                     # Glassmorphic stylesheet, tabs & modal styling
│   └── app.js                      # Analytics rendering & complaint workflow
├── database/
│   └── airguard.db                 # SQLite database file
├── .env.example                    # Environment configuration template
├── .gitignore                      # Git exclusion rules
└── README.md                       # Documentation
```

---

## Environment Setup & Configuration

### 1. Copy Environment Template

```bash
cp .env.example .env
```

### 2. Configure Environment Variables in `.env`

```env
# Google Air Quality API Key (Optional)
# If empty, SkyCheck automatically uses the global Open-Meteo atmospheric station network
GOOGLE_AIR_QUALITY_API_KEY=

# SMTP Email Provider Credentials (Optional for testing, required for live email delivery)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com

# Cache Settings
CACHE_TTL_SECONDS=300
```

> **Note on Gmail:** If using Gmail for SMTP, generate an **App Password** via Google Account Settings -> Security -> 2-Step Verification -> App passwords. Use this 16-character code as `SMTP_PASSWORD`.
>
> **Development / Test Mode:** If `SMTP_USERNAME` and `SMTP_PASSWORD` are left blank, SkyCheck automatically activates **Development Test Mode (Mock Dispatch)**. Complaints are validated, logged to SQLite with a `SKY-TEST-XXXX` reference code, and confirmed in the UI without sending live emails.

---

## Running the Application

### 1. Start Backend API Server

```bash
cd backend
python app.py
```
The server will start on `http://127.0.0.1:5000`.

### 2. Open the Frontend

Open `frontend/index.html` in your web browser or navigate to `http://127.0.0.1:5000/`.

---

## How to Test

### 1. Testing Historical Analytics (Feature A)
1. Search for **CGS Colony** or select it from popular pills.
2. In the **Historical Analytics** section:
   - Click **7D**, **14D**, or **30D** to view multi-day real atmospheric trends.
   - Click **AQI Trend**, **PM2.5**, **PM10**, or **Compare All** to view overlaid pollutant curves.
   - Hover over chart data points to view the interactive tooltip with date, day, AQI, and CPCB category.
   - Check the **Trend & Change** card and narrative text for percentage change calculations.

### 2. Testing Pollution Complaints (Feature B)
1. Click the blue **Report Air Pollution / Send Complaint** button on the dashboard.
2. Verify that **CGS Colony, Mumbai** is resolved to **BMC Ward F/North Office (`ac.fn@mcgm.gov.in`)**.
3. Enter your email address (e.g. `citizen@example.com`).
4. Select a pollution source (e.g. `Construction Dust & Uncovered Debris`).
5. Type a description or click a quick insert chip (e.g. `Toxic Smoke`).
6. *(Optional)* Click or drag a photo into the upload drop zone to test evidence attachment.
7. Check the citizen consent authorization box.
8. Click **Send Complaint to Authority**.
9. Confirm that the success screen displays the generated **Complaint Reference ID** (e.g. `SKY-TEST-2026-XXXX`) and confirmed authority.
10. Click **Copy Reference ID** to test clipboard integration.
11. Attempt to immediately submit the same report again to verify the anti-duplicate guard (`DUPLICATE_SUBMISSION`).

---

## Authority Directory & Verification Status

| Authority / Jurisdiction | Scope / Localities | Official Email | Official Source | Status |
| :--- | :--- | :--- | :--- | :--- |
| **BMC Ward F/North** | Antop Hill, Wadala, Matunga, Sion, CGS Colony | `ac.fn@mcgm.gov.in` | `portal.mcgm.gov.in` | Verified (Mar 2026) |
| **BMC Ward F/South** | Parel, Sewri, Lalbaug, Naigaon | `ac.fs@mcgm.gov.in` | `portal.mcgm.gov.in` | Verified (Mar 2026) |
| **BMC Ward A** | Colaba, Fort, Nariman Point, Churchgate | `ac.a@mcgm.gov.in` | `portal.mcgm.gov.in` | Verified (Mar 2026) |
| **BMC Ward G/South** | Worli, Lower Parel, Prabhadevi | `ac.gs@mcgm.gov.in` | `portal.mcgm.gov.in` | Verified (Mar 2026) |
| **BMC Ward H/West** | Bandra West, Khar West, Santacruz West | `ac.hw@mcgm.gov.in` | `portal.mcgm.gov.in` | Verified (Mar 2026) |
| **BMC Ward K/West** | Andheri West, Juhu, Versova, Oshiwara | `ac.kw@mcgm.gov.in` | `portal.mcgm.gov.in` | Verified (Mar 2026) |
| **BMC Ward K/East** | Andheri East, Jogeshwari East, Marol | `ac.ke@mcgm.gov.in` | `portal.mcgm.gov.in` | Verified (Mar 2026) |
| **BMC Central Environment** | General Mumbai (Unmapped Wards) | `dmc.env@mcgm.gov.in` | `portal.mcgm.gov.in` | Fallback Verified |
| **MPCB Regional Office Mumbai** | Mumbai City & Suburban | `romumbai@mpcb.gov.in` | `mpcb.gov.in` | Verified (Mar 2026) |
| **Pune Municipal Corp (PMC)** | Pune City | `info@pmc.gov.in` | `pmc.gov.in` | Verified (Mar 2026) |
| **Thane Municipal Corp (TMC)** | Thane City | `commissioner@thanecity.gov.in` | `thanecity.gov.in` | Verified (Mar 2026) |
| **KDMC** | Kalyan, Dombivli | `commissioner@kdmc.gov.in` | `kdmc.gov.in` | Verified (Mar 2026) |
| **Delhi DPCC & CPCB SAMEER** | NCT of Delhi / NCR | `msdpcc@nic.in` | `dpcc.delhigovt.nic.in` | Verified (Mar 2026) |
| **Karnataka KSPCB & BBMP** | Bengaluru Urban & Karnataka | `membersecretary@kspcb.gov.in` | `kspcb.karnataka.gov.in` | Verified (Mar 2026) |
| **Tamil Nadu TNPCB** | Chennai & Tamil Nadu | `tnpcb-chn@gov.in` | `tnpcb.gov.in` | Verified (Mar 2026) |
| **Telangana TGSPCB** | Hyderabad & Telangana | `ms-tspcb@telangana.gov.in` | `tspcb.capp.co.in` | Verified (Mar 2026) |
| **West Bengal WBPCB** | Kolkata & West Bengal | `membersecretary@wbpcb.gov.in` | `wbpcb.gov.in` | Verified (Mar 2026) |
| **Gujarat GPCB** | Ahmedabad & Gujarat | `ms-gpcb@gujarat.gov.in` | `gpcb.gujarat.gov.in` | Verified (Mar 2026) |
| **Uttar Pradesh UPPCB** | Lucknow & Uttar Pradesh | `ms@uppcb.com` | `uppcb.com` | Verified (Mar 2026) |
| **CPCB National Directorate** | All Indian States & UTs | `cpcb@nic.in` | `sameer.cpcb.gov.in` | National Fallback |
