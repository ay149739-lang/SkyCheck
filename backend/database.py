"""
database.py - SQLite setup and helper functions for SkyCheck
Database: database/airguard.db
Tables: locations, aqi_history, search_history, authorities, email_reports, complaints
"""

import sqlite3
import os
import json
import hashlib
from datetime import datetime, timedelta
from config import DB_PATH


def get_connection():
    """Return a thread-safe SQLite connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't already exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS locations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT    NOT NULL,
            display_name TEXT,
            locality     TEXT,
            city         TEXT,
            district     TEXT,
            state        TEXT,
            country      TEXT,
            latitude     REAL    NOT NULL,
            longitude    REAL    NOT NULL,
            created_at   TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS aqi_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            location_name TEXT    NOT NULL,
            latitude      REAL    NOT NULL,
            longitude     REAL    NOT NULL,
            timestamp     TEXT    NOT NULL,
            aqi           REAL,
            category      TEXT,
            pm25          REAL,
            pm10          REAL,
            no2           REAL,
            so2           REAL,
            co            REAL,
            o3            REAL,
            nh3           REAL,
            created_at    TEXT    DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_aqi_history_coords_time
        ON aqi_history(latitude, longitude, timestamp);

        CREATE TABLE IF NOT EXISTS search_history (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            query         TEXT    NOT NULL,
            resolved_name TEXT,
            latitude      REAL,
            longitude     REAL,
            timestamp     TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS authorities (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            auth_key             TEXT    UNIQUE,
            city                 TEXT,
            district             TEXT,
            state                TEXT,
            ward_code            TEXT,
            authority_name       TEXT    NOT NULL,
            authority_type       TEXT    DEFAULT 'municipal_corporation',
            jurisdiction_scope   TEXT,
            email                TEXT,
            secondary_email      TEXT,
            escalation_authority TEXT,
            website              TEXT,
            portal_url           TEXT,
            official_source_url  TEXT,
            verification_date    TEXT,
            verification_status  TEXT    DEFAULT 'verified',
            notes                TEXT,
            active               INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS email_reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            location   TEXT    NOT NULL,
            authority  TEXT,
            recipient  TEXT,
            aqi        REAL,
            sent_at    TEXT    DEFAULT (datetime('now')),
            status     TEXT    DEFAULT 'pending',
            error_msg  TEXT
        );

        CREATE TABLE IF NOT EXISTS complaints (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_id               TEXT    UNIQUE NOT NULL,
            created_at           TEXT    DEFAULT (datetime('now')),
            user_email_masked    TEXT    NOT NULL,
            user_email_hash      TEXT    NOT NULL,
            location_name        TEXT    NOT NULL,
            locality             TEXT,
            ward                 TEXT,
            city                 TEXT,
            district             TEXT,
            state                TEXT,
            latitude             REAL,
            longitude            REAL,
            aqi                  REAL,
            category             TEXT,
            pm25                 REAL,
            pm10                 REAL,
            dominant_pollutant   TEXT,
            pollution_source     TEXT,
            complaint_description TEXT   NOT NULL,
            has_photo_evidence   INTEGER DEFAULT 0,
            photo_filename       TEXT,
            authority_name       TEXT    NOT NULL,
            authority_type       TEXT,
            authority_email      TEXT,
            routing_level        TEXT,
            routing_reason       TEXT,
            send_status          TEXT    NOT NULL,
            provider_response    TEXT,
            error_message        TEXT,
            client_ip            TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_complaints_email_hash
        ON complaints(user_email_hash, created_at);
    """)

    # Check and migrate authorities table columns if old schema exists
    cur.execute("PRAGMA table_info(authorities)")
    existing_cols = {row["name"] for row in cur.fetchall()}
    needed_cols = {
        "auth_key": "TEXT UNIQUE",
        "ward_code": "TEXT",
        "authority_type": "TEXT DEFAULT 'municipal_corporation'",
        "jurisdiction_scope": "TEXT",
        "secondary_email": "TEXT",
        "escalation_authority": "TEXT",
        "portal_url": "TEXT",
        "official_source_url": "TEXT",
        "verification_date": "TEXT",
        "verification_status": "TEXT DEFAULT 'verified'",
        "notes": "TEXT"
    }

    if "auth_key" not in existing_cols:
        # Safely migrate table
        cur.execute("DROP TABLE IF EXISTS authorities")
        cur.execute("""
            CREATE TABLE authorities (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                auth_key             TEXT    UNIQUE,
                city                 TEXT,
                district             TEXT,
                state                TEXT,
                ward_code            TEXT,
                authority_name       TEXT    NOT NULL,
                authority_type       TEXT    DEFAULT 'municipal_corporation',
                jurisdiction_scope   TEXT,
                email                TEXT,
                secondary_email      TEXT,
                escalation_authority TEXT,
                website              TEXT,
                portal_url           TEXT,
                official_source_url  TEXT,
                verification_date    TEXT,
                verification_status  TEXT    DEFAULT 'verified',
                notes                TEXT,
                active               INTEGER DEFAULT 1
            )
        """)

    conn.commit()
    conn.close()
    print("[DB] airguard.db schema verified.")


def mask_email(email: str) -> str:
    """Mask email for privacy compliance (e.g., ad***a@gmail.com)."""
    if not email or "@" not in email:
        return "citizen@protected"
    user, domain = email.split("@", 1)
    if len(user) <= 2:
        masked_user = user[0] + "*"
    else:
        masked_user = user[:2] + "***" + user[-1]
    return f"{masked_user}@{domain}"


def hash_email(email: str) -> str:
    """Hash email for anti-duplicate tracking without exposing address."""
    if not email:
        return ""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def check_recent_complaint(email_hash: str, location_name: str, minutes: int = 5) -> bool:
    """Check if the same user submitted a complaint for the same location recently."""
    if not email_hash:
        return False
    conn = get_connection()
    cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute("""
        SELECT COUNT(*) as cnt FROM complaints
        WHERE user_email_hash = ? AND (location_name = ? OR ? = '')
        AND created_at >= ?
    """, (email_hash, location_name, location_name, cutoff)).fetchone()
    conn.close()
    return bool(row and row["cnt"] > 0)


def save_complaint(complaint_dict: dict) -> str:
    """Persist an official citizen pollution complaint record."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO complaints (
            ref_id, user_email_masked, user_email_hash,
            location_name, locality, ward, city, district, state,
            latitude, longitude, aqi, category, pm25, pm10, dominant_pollutant,
            pollution_source, complaint_description, has_photo_evidence, photo_filename,
            authority_name, authority_type, authority_email,
            routing_level, routing_reason, send_status, provider_response, error_message, client_ip
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        )
    """, (
        complaint_dict.get("ref_id"),
        complaint_dict.get("user_email_masked"),
        complaint_dict.get("user_email_hash"),
        complaint_dict.get("location_name", "Unknown"),
        complaint_dict.get("locality"),
        complaint_dict.get("ward"),
        complaint_dict.get("city"),
        complaint_dict.get("district"),
        complaint_dict.get("state"),
        complaint_dict.get("latitude"),
        complaint_dict.get("longitude"),
        complaint_dict.get("aqi"),
        complaint_dict.get("category"),
        complaint_dict.get("pm25"),
        complaint_dict.get("pm10"),
        complaint_dict.get("dominant_pollutant"),
        complaint_dict.get("pollution_source"),
        complaint_dict.get("complaint_description", ""),
        1 if complaint_dict.get("has_photo_evidence") else 0,
        complaint_dict.get("photo_filename"),
        complaint_dict.get("authority_name", "Environmental Authority"),
        complaint_dict.get("authority_type"),
        complaint_dict.get("authority_email"),
        complaint_dict.get("routing_level"),
        complaint_dict.get("routing_reason"),
        complaint_dict.get("send_status", "pending"),
        complaint_dict.get("provider_response"),
        complaint_dict.get("error_message"),
        complaint_dict.get("client_ip")
    ))

    conn.commit()
    conn.close()
    return complaint_dict.get("ref_id")


def save_search(query: str, resolved_name: str, lat: float, lon: float):
    conn = get_connection()
    conn.execute(
        "INSERT INTO search_history (query, resolved_name, latitude, longitude) VALUES (?,?,?,?)",
        (query, resolved_name, lat, lon)
    )
    conn.commit()
    conn.close()


def save_aqi_snapshot(loc: str, lat: float, lon: float, ts: str, data: dict):
    if not ts:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    # Check if a snapshot for same approximate lat/lon and day already exists
    day_prefix = ts[:10]
    existing = conn.execute("""
        SELECT id FROM aqi_history
        WHERE abs(latitude - ?) < 0.05 AND abs(longitude - ?) < 0.05
        AND timestamp LIKE ?
        LIMIT 1
    """, (lat, lon, f"{day_prefix}%")).fetchone()

    p = data.get("pollutants", {})
    pm25 = p.get("pm25", data.get("pm25"))
    pm10 = p.get("pm10", data.get("pm10"))
    no2 = p.get("no2", data.get("no2"))
    so2 = p.get("so2", data.get("so2"))
    co = p.get("co", data.get("co"))
    o3 = p.get("o3", data.get("o3"))
    nh3 = p.get("nh3", data.get("nh3"))

    if existing:
        conn.execute("""
            UPDATE aqi_history
            SET location_name=?, aqi=?, category=?, pm25=?, pm10=?, no2=?, so2=?, co=?, o3=?, nh3=?, timestamp=?
            WHERE id=?
        """, (
            loc, data.get("aqi"), data.get("category"),
            pm25, pm10, no2, so2, co, o3, nh3, ts, existing["id"]
        ))
    else:
        conn.execute("""
            INSERT INTO aqi_history
                (location_name, latitude, longitude, timestamp, aqi, category,
                 pm25, pm10, no2, so2, co, o3, nh3)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            loc, lat, lon, ts,
            data.get("aqi"), data.get("category"),
            pm25, pm10, no2, so2, co, o3, nh3
        ))
    conn.commit()
    conn.close()


def get_cached_history_snapshots(lat: float, lon: float, days: int = 7):
    """Retrieve persisted daily historical readings from SQLite for a coordinate."""
    conn = get_connection()
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT * FROM aqi_history
        WHERE abs(latitude - ?) < 0.08 AND abs(longitude - ?) < 0.08
        AND timestamp >= ?
        ORDER BY timestamp ASC
    """, (lat, lon, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_email_report(location: str, authority: str, recipient: str,
                        aqi: float, status: str = "pending") -> int:
    """Create a pending email report entry and return its primary key id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO email_reports (location, authority, recipient, aqi, status, error_msg)
        VALUES (?, ?, ?, ?, ?, NULL)
    """, (location or "Unknown", authority or "N/A", recipient or "N/A", aqi, status))
    report_id = cur.lastrowid
    conn.commit()
    conn.close()
    return report_id


def update_email_report(report_id: int, status: str, error_msg: str = None):
    """Update email report status to 'sent' or 'failed' with timestamp and safe diagnostic message."""
    conn = get_connection()
    conn.execute("""
        UPDATE email_reports
        SET status = ?, error_msg = ?, sent_at = datetime('now')
        WHERE id = ?
    """, (status, error_msg, report_id))
    conn.commit()
    conn.close()


def save_email_report(location: str, authority: str, recipient: str,
                      aqi: float, status: str, error: str = None) -> int:
    """Directly insert a completed or failed email report record."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO email_reports (location, authority, recipient, aqi, status, error_msg)
        VALUES (?,?,?,?,?,?)
    """, (location, authority, recipient, aqi, status, error))
    report_id = cur.lastrowid
    conn.commit()
    conn.close()
    return report_id


def get_recent_email_reports(limit: int = 20) -> list:
    """Retrieve recent email delivery report records for auditing."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, location, authority, recipient, aqi, sent_at, status, error_msg
        FROM email_reports
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def find_authority(city: str = None, district: str = None, state: str = None):
    """Forward to unified authority_service."""
    from services.authority_service import resolve_authority_for_location
    return resolve_authority_for_location(locality="", city=city or "", district=district or "", state=state or "")


def seed_authorities():
    """Seed authorities table from verified JSON directory."""
    conn = get_connection()
    cur = conn.cursor()

    mapping_path = os.path.join(os.path.dirname(__file__), "data", "authority_mapping.json")
    if not os.path.exists(mapping_path):
        conn.close()
        return

    with open(mapping_path, "r", encoding="utf-8") as f:
        entries = json.load(f)

    # Re-sync authorities table with current mapping
    for e in entries:
        auth_key = e.get("id") or f"{e.get('city', '')}_{e.get('authority_name', '')}"
        cur.execute("""
            INSERT INTO authorities (
                auth_key, city, district, state, ward_code, authority_name,
                authority_type, jurisdiction_scope, email, secondary_email,
                escalation_authority, website, portal_url, official_source_url,
                verification_date, verification_status, notes, active
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(auth_key) DO UPDATE SET
                city=excluded.city,
                district=excluded.district,
                state=excluded.state,
                ward_code=excluded.ward_code,
                authority_name=excluded.authority_name,
                authority_type=excluded.authority_type,
                jurisdiction_scope=excluded.jurisdiction_scope,
                email=excluded.email,
                secondary_email=excluded.secondary_email,
                escalation_authority=excluded.escalation_authority,
                website=excluded.website,
                portal_url=excluded.portal_url,
                official_source_url=excluded.official_source_url,
                verification_date=excluded.verification_date,
                verification_status=excluded.verification_status,
                notes=excluded.notes,
                active=excluded.active
        """, (
            auth_key, e.get("city"), e.get("district"), e.get("state"),
            e.get("ward_code"), e.get("authority_name"), e.get("authority_type"),
            e.get("jurisdiction_scope"), e.get("email"), e.get("secondary_email"),
            e.get("escalation_authority"), e.get("website"), e.get("portal_url"),
            e.get("official_source_url"), e.get("verification_date"),
            e.get("verification_status", "verified"), e.get("notes"), 1
        ))

    conn.commit()
    conn.close()
    print(f"[DB] Seeded and verified {len(entries)} environmental authority directories.")
