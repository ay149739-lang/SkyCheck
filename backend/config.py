"""
config.py - Environment variable loader for SkyCheck
All secrets are loaded from .env - never hardcoded in source code.
"""

import os
from dotenv import load_dotenv

# Load .env from project root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))

# ── Google Maps Platform ───────────────────────────────────
GOOGLE_AIR_QUALITY_API_KEY = os.getenv("GOOGLE_AIR_QUALITY_API_KEY", "")

# ── SMTP / Email ───────────────────────────────────────────
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)

# ── App Settings ───────────────────────────────────────────
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 minutes
DB_PATH = os.path.join(_ROOT, "database", "airguard.db")

def google_aq_key_configured() -> bool:
    return bool(GOOGLE_AIR_QUALITY_API_KEY)

def smtp_configured() -> bool:
    return all([SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD])

def validate_smtp_credentials() -> tuple:
    """Check if all required SMTP settings are present in environment."""
    missing = []
    if not SMTP_HOST:
        missing.append("SMTP_HOST")
    if not SMTP_PORT:
        missing.append("SMTP_PORT")
    if not SMTP_USERNAME:
        missing.append("SMTP_USERNAME")
    if not SMTP_PASSWORD:
        missing.append("SMTP_PASSWORD")

    if missing:
        return False, f"Missing required SMTP setting(s) in .env: {', '.join(missing)}"
    return True, "SMTP settings present"
