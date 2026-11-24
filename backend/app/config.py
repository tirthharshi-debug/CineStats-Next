"""
Central runtime configuration, read from environment variables.

Local development loads ``backend/.env``; production (Render) uses real
environment variables. Nothing secret has a default value.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

logger = logging.getLogger("cinestats.config")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring non-integer %s=%r; using %s", name, raw, default)
        return default
    return value if value > 0 else default


def _csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"

# Where SQLite files and temporary uploads live. On Render, point this at a
# persistent disk mount (for example /var/data) if you want the TMDB cache to
# survive deploys. The cache is rebuildable, so an ephemeral disk is acceptable.
DATA_DIR = Path(os.getenv("DATA_DIR") or BACKEND_DIR)

CORS_ALLOWED_ORIGINS = _csv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
CORS_CONFIGURED = bool(os.getenv("CORS_ALLOWED_ORIGINS", "").strip())
ALLOWED_HOSTS = _csv("ALLOWED_HOSTS")  # empty = do not enforce Host header

# Upload and processing limits.
MAX_UPLOAD_BYTES = _int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
MAX_ACTIVE_JOBS = _int("MAX_ACTIVE_JOBS", 2)
MAX_UNIQUE_MOVIES = _int("MAX_UNIQUE_MOVIES", 6000)
JOB_TTL_SECONDS = _int("JOB_TTL_SECONDS", 1800)
JOB_CLEANUP_INTERVAL_SECONDS = _int("JOB_CLEANUP_INTERVAL_SECONDS", 300)

# Per-IP rate limits (in-memory, per process).
UPLOADS_PER_HOUR = _int("UPLOADS_PER_HOUR", 20)
POLLS_PER_MINUTE = _int("POLLS_PER_MINUTE", 300)
EXPORTS_PER_MINUTE = _int("EXPORTS_PER_MINUTE", 10)

# Number of reverse proxies in front of the app that append to X-Forwarded-For.
# 0 = ignore the header and use the socket address (safe default).
TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "0") or 0)

# How long a "TMDB found nothing" result is remembered before searching again.
TMDB_MISS_TTL_DAYS = _int("TMDB_MISS_TTL_DAYS", 7)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
