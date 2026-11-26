"""
FastAPI application entry point.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import config  # loads backend/.env before anything reads the environment
from app.database.db import init_db
from app.routes import api
from app.security import RequestSizeLimitMiddleware, SecurityHeadersMiddleware
from app.services import job_store

import os

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cinestats")


def _validate_production_settings() -> None:
    """Fail fast on a misconfigured production deploy instead of failing per request."""
    if not config.IS_PRODUCTION:
        return
    problems = []
    if not (os.getenv("TMDB_API_KEY") or os.getenv("TMDB_READ_ACCESS_TOKEN")):
        problems.append("TMDB_API_KEY (or TMDB_READ_ACCESS_TOKEN) is not set")
    if not config.CORS_CONFIGURED:
        problems.append("CORS_ALLOWED_ORIGINS is not set (set it to your frontend URL)")
    if any("localhost" in o or "127.0.0.1" in o for o in config.CORS_ALLOWED_ORIGINS):
        problems.append("CORS_ALLOWED_ORIGINS still contains a localhost origin")
    if problems:
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))
    if config.TRUSTED_PROXY_HOPS == 0:
        logger.warning(
            "TRUSTED_PROXY_HOPS is 0 in production; per-IP rate limiting will see the proxy IP instead of client IPs"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    _validate_production_settings()
    await init_db()
    await job_store.init()
    interrupted = await job_store.fail_interrupted()
    if interrupted:
        logger.warning("Marked %d interrupted job(s) as failed after restart", interrupted)
    cleanup_task = asyncio.create_task(api.cleanup_old_jobs())
    logger.info(
        "Started in %s mode (TMDB credentials %s)",
        config.APP_ENV,
        "loaded" if (os.getenv("TMDB_API_KEY") or os.getenv("TMDB_READ_ACCESS_TOKEN")) else "MISSING",
    )
    yield
    pending = [cleanup_task, *list(api._background_tasks)]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    logger.info("Shutting down")


# Interactive API docs are handy locally but needlessly expose the API surface
# on a public deployment.
app = FastAPI(
    title="CineStats API",
    description="Analyze your Letterboxd export with TMDB-enriched analytics",
    version="1.1.0",
    lifespan=lifespan,
    docs_url=None if config.IS_PRODUCTION else "/docs",
    redoc_url=None,
    openapi_url=None if config.IS_PRODUCTION else "/openapi.json",
)

# Middleware runs outermost-last: CORS must wrap everything so error responses
# (413, 429, 500) still carry CORS headers the browser can read.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
if config.ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-Job-Token"],
    expose_headers=["Retry-After", "Content-Disposition"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log details server-side; never leak internals to clients."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)


# Mount routes
app.include_router(api.router, prefix="/api")
