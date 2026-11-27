"""
Central runtime configuration, read from environment variables.

Local development loads ``backend/.env``; production uses real
environment variables. Nothing secret has a default value.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

logger = logging.getLogger("cinestats.config")


def _int(name: str, default: int, *, allow_zero: bool = False) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring non-integer %s=%r; using %s", name, raw, default)
        return default
    if value > 0 or (allow_zero and value == 0):
        return value
    return default


def _csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"

# Directory for SQLite files and temporary uploads; point at a persistent disk in production if needed.
DATA_DIR = Path(os.getenv("DATA_DIR") or BACKEND_DIR)

CORS_ALLOWED_ORIGINS = _csv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
CORS_CONFIGURED = bool(os.getenv("CORS_ALLOWED_ORIGINS", "").strip())
ALLOWED_HOSTS = _csv("ALLOWED_HOSTS")  # empty = do not enforce Host header

# Upload and processing limits.
MAX_UPLOAD_BYTES = _int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)
MAX_ACTIVE_JOBS = _int("MAX_ACTIVE_JOBS", 2)
MAX_QUEUED_JOBS = _int("MAX_QUEUED_JOBS", 3, allow_zero=True)
QUEUE_WAIT_TIMEOUT_SECONDS = _int("QUEUE_WAIT_TIMEOUT_SECONDS", 300)
MAX_UNIQUE_MOVIES = _int("MAX_UNIQUE_MOVIES", 6000)
JOB_TTL_SECONDS = _int("JOB_TTL_SECONDS", 1800)
JOB_CLEANUP_INTERVAL_SECONDS = _int("JOB_CLEANUP_INTERVAL_SECONDS", 300)

# Per-IP rate limits (in-memory, per process).
UPLOADS_PER_HOUR = _int("UPLOADS_PER_HOUR", 20)
POLLS_PER_MINUTE = _int("POLLS_PER_MINUTE", 300)
EXPORTS_PER_MINUTE = _int("EXPORTS_PER_MINUTE", 10)

# Number of reverse proxies in front of the app that append to X-Forwarded-For.
# 0 = ignore the header and use the socket address (safe default).
TRUSTED_PROXY_HOPS = _int("TRUSTED_PROXY_HOPS", 0, allow_zero=True)

# How long a "TMDB found nothing" result is remembered before searching again.
TMDB_MISS_TTL_DAYS = _int("TMDB_MISS_TTL_DAYS", 7)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
