import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = os.getenv("TRIAD_DB_PATH", str(PROJECT_ROOT / "backend" / "triad.db"))

AGENT0_BASE_URL = os.getenv("AGENT0_BASE_URL", "http://localhost:80").rstrip("/")
AGENT0_API_KEY = os.getenv("AGENT0_API_KEY", "").strip()
AGENT0_PROJECT_NAME = os.getenv("AGENT0_PROJECT_NAME", "dashboard_triad_project").strip()
AGENT0_LIFETIME_HOURS = int(os.getenv("AGENT0_LIFETIME_HOURS", "2"))

# Security: by default only local dev origins.
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if o.strip()
]

# Basic input safety limits
MAX_PROMPT_SIZE = int(os.getenv("MAX_PROMPT_SIZE", "50000"))
MAX_GOAL_SIZE = int(os.getenv("MAX_GOAL_SIZE", "10000"))
MAX_CONTEXT_SIZE = int(os.getenv("MAX_CONTEXT_SIZE", "50000"))
