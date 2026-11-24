"""
Security helpers: response headers, request-size guard, per-IP rate limiting,
and job access tokens.
"""
import hashlib
import hmac
import logging
import re
import secrets
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app import config

logger = logging.getLogger("cinestats.security")

JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")


# ─── Job tokens ──────────────────────────────────────────────────────────────

def new_job_token() -> str:
    """Return an unguessable per-job access token (shown to the uploader once)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str | None, expected_hash: str | None) -> bool:
    if not token or not expected_hash or len(token) > 200:
        return False
    return hmac.compare_digest(hash_token(token), expected_hash)


# ─── Client identification ───────────────────────────────────────────────────

def client_ip(request: Request) -> str:
    """
    Best-effort client IP. X-Forwarded-For is trusted only when
    TRUSTED_PROXY_HOPS > 0, and then only the entry added by our own proxy
    chain (counting from the right) is used, so clients cannot spoof it.
    """
    hops = config.TRUSTED_PROXY_HOPS
    if hops > 0:
        header = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in header.split(",") if p.strip()]
        if len(parts) >= hops:
            return parts[-hops]
    return request.client.host if request.client else "unknown"


# ─── Rate limiting ───────────────────────────────────────────────────────────

class RateLimiter:
    """Sliding-window limiter keyed by (bucket, client). In-memory, per process."""

    def __init__(self):
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def check(self, bucket: str, client: str, limit: int, window: float) -> float:
        """Record a hit. Returns 0 if allowed, else seconds until retry."""
        now = time.monotonic()
        hits = self._hits[(bucket, client)]
        cutoff = now - window
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= limit:
            return max(1.0, hits[0] + window - now)
        hits.append(now)
        self._sweep(now, window)
        return 0.0

    def _sweep(self, now: float, window: float) -> None:
        # Occasionally drop idle keys so the dict cannot grow without bound.
        if now - self._last_sweep < 300:
            return
        self._last_sweep = now
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - max(window, 3600)]:
            self._hits.pop(key, None)

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


def rate_limit(bucket: str, limit_getter, window: float):
    """FastAPI dependency factory. ``limit_getter`` is read per request."""

    async def dependency(request: Request):
        client = client_ip(request)
        retry_after = limiter.check(bucket, client, limit_getter(), window)
        if retry_after:
            logger.warning("Rate limit hit: bucket=%s client=%s", bucket, client)
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

    return dependency


# ─── Middleware ──────────────────────────────────────────────────────────────

_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        headers = response.headers
        headers["X-Content-Type-Options"] = "nosniff"
        headers["Referrer-Policy"] = "no-referrer"
        headers["X-Frame-Options"] = "DENY"
        headers["Cross-Origin-Resource-Policy"] = "same-site"
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api"):
            headers["Cache-Control"] = "no-store"
        # The JSON API never needs to load anything; interactive docs (dev only) do.
        if not request.url.path.startswith(_DOC_PATHS):
            headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if config.IS_PRODUCTION:
            headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized bodies up front using Content-Length (cheap, early)."""

    async def dispatch(self, request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            declared = request.headers.get("content-length")
            # Multipart framing adds a little overhead beyond the file itself.
            limit = config.MAX_UPLOAD_BYTES + 64 * 1024
            if declared and declared.isdigit() and int(declared) > limit:
                return JSONResponse(
                    {"detail": "CineStats currently supports Letterboxd exports up to 10 MB."},
                    status_code=413,
                )
        return await call_next(request)
