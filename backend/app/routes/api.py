"""
API routes for the Letterboxd analytics application.

Each upload creates a job with its own unguessable access token. Every job
endpoint requires that token (``X-Job-Token`` header), so knowing or guessing
a job ID is not enough to read someone else's analysis. Heavy CPU work (pandas,
PDF rendering) runs in worker threads so the event loop stays responsive.
"""
import asyncio
import logging
import math
import os
import shutil
import time
import uuid
import zipfile

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app import config, security
from app.services import job_store
from app.services.file_service import (
    extract_zip, validate_letterboxd_export,
    parse_diary, parse_ratings, parse_watched,
    parse_lists, get_unique_movies
)
from app.services.tmdb_service import TMDBService
from app.services.stats_service import (
    compute_basic_stats, compute_pro_stats,
    compute_patron_stats, compute_advanced_stats,
    compute_community_comparison, compute_binge_stats,
    compute_monthly_activity, compute_decade_leaderboard
)

logger = logging.getLogger("cinestats.api")

router = APIRouter()

# ─── Per-job state ───
# Live progress is kept in memory; durable records live in job_store.
_jobs: dict[str, dict] = {}
_background_tasks: set[asyncio.Task] = set()

ACTIVE_STATUSES = {"idle", "extracting", "parsing", "enriching", "computing"}
GENERIC_FAILURE = (
    "The archive could not be processed. Check that it is a valid "
    "Letterboxd export and try again."
)

BAD_ZIP_MESSAGE = "That file isn't a readable ZIP archive. Please upload the original export from Letterboxd."

_poll_limit = security.rate_limit("poll", lambda: config.POLLS_PER_MINUTE, 60)
_upload_limit = security.rate_limit("upload", lambda: config.UPLOADS_PER_HOUR, 3600)
_export_limit = security.rate_limit("export", lambda: config.EXPORTS_PER_MINUTE, 60)


def _json_safe(value):
    """Make values strictly JSON-safe: numpy scalars to Python, NaN/inf to None."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, TypeError):
            return str(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _active_job_count() -> int:
    return sum(job["status"] in ACTIVE_STATUSES for job in _jobs.values())


def _new_job() -> tuple[str, str, dict]:
    """Create a job; returns (job_id, plaintext_token, job_state)."""
    job_id = uuid.uuid4().hex
    token = security.new_job_token()
    job = {
        "status": "idle",        # idle | extracting | parsing | enriching | computing | done | error
        "current": 0,
        "total": 0,
        "result": None,
        "error": None,
        "token_hash": security.hash_token(token),
        "created_at": time.time(),
        "finished_at": None,
    }
    _jobs[job_id] = job
    return job_id, token, job


async def _persist(job_id: str, job: dict) -> None:
    """Best-effort write-through; a storage hiccup must not fail the analysis."""
    try:
        await job_store.save(
            job_id, job["token_hash"], job["status"], job["created_at"],
            error=job["error"], result=job["result"], finished_at=job["finished_at"],
        )
    except Exception:
        logger.exception("Could not persist job %s", job_id)


async def _authorized_job(job_id: str, x_job_token: str | None = Header(default=None)) -> tuple[str, dict]:
    """
    Resolve a job from its ID and access token. Unknown IDs, bad tokens and
    malformed IDs all return the same 404 so job IDs cannot be probed.
    """
    not_found = HTTPException(status_code=404, detail="Job not found")
    if not security.JOB_ID_RE.match(job_id or ""):
        raise not_found

    job = _jobs.get(job_id)
    if job is None:
        record = await job_store.load(job_id)  # survives restarts
        if record is None or not security.token_matches(x_job_token, record["token_hash"]):
            raise not_found
        job = {
            "status": record["status"], "current": 0, "total": 0,
            "result": record["result"], "error": record["error"],
            "token_hash": record["token_hash"], "created_at": record["created_at"],
            "finished_at": record["finished_at"],
        }
        _jobs[job_id] = job
        return job_id, job

    if not security.token_matches(x_job_token, job["token_hash"]):
        raise not_found
    return job_id, job


async def cleanup_old_jobs():
    """Periodically remove finished jobs older than the TTL, in memory and on disk."""
    while True:
        await asyncio.sleep(config.JOB_CLEANUP_INTERVAL_SECONDS)
        try:
            now = time.time()
            expired = [
                jid for jid, job in _jobs.items()
                if job["status"] in ("done", "error")
                and job.get("finished_at")
                and (now - job["finished_at"]) > config.JOB_TTL_SECONDS
            ]
            for jid in expired:
                _jobs.pop(jid, None)
            purged = await job_store.purge_expired(config.JOB_TTL_SECONDS)
            if expired or purged:
                logger.info("Cleanup evicted %d in-memory and %d stored job(s)", len(expired), purged)
        except Exception:
            logger.exception("Job cleanup failed")


async def _process_in_background(job_id: str, file_bytes: bytes):
    """Run the full pipeline in the background for a specific job."""
    job = _jobs[job_id]
    extract_path = None
    try:
        job["status"] = "extracting"

        # 1. Extract ZIP (CPU + disk work: keep it off the event loop)
        extract_path = await asyncio.to_thread(extract_zip, file_bytes)
        file_bytes = b""  # the raw upload is no longer needed

        await asyncio.to_thread(validate_letterboxd_export, extract_path)

        job["status"] = "parsing"

        # 2. Parse CSVs
        diary_df = await asyncio.to_thread(parse_diary, extract_path)
        ratings_df = await asyncio.to_thread(parse_ratings, extract_path)
        watched_df = await asyncio.to_thread(parse_watched, extract_path)
        lists_data = await asyncio.to_thread(parse_lists, extract_path)

        # 3. Compute basic + pro stats immediately (no TMDB needed)
        basic_stats = await asyncio.to_thread(compute_basic_stats, diary_df, ratings_df, watched_df)
        pro_stats = await asyncio.to_thread(compute_pro_stats, diary_df, ratings_df)

        # 4. Get unique movies for TMDB enrichment
        unique_movies = await asyncio.to_thread(get_unique_movies, diary_df, watched_df, ratings_df)
        if len(unique_movies) > config.MAX_UNIQUE_MOVIES:
            raise ValueError(
                f"This export lists {len(unique_movies):,} different films, which is over the "
                f"current limit of {config.MAX_UNIQUE_MOVIES:,}."
            )
        job["total"] = len(unique_movies)
        job["status"] = "enriching"

        # 5. Enrich movies via TMDB (this is the slow part)
        tmdb_service = TMDBService()

        async def update_progress(current: int, total: int):
            job["current"] = current
            job["total"] = total

        try:
            enriched = await tmdb_service.enrich_batch(unique_movies, update_progress)
        finally:
            await tmdb_service.close()

        job["status"] = "computing"

        # 6. Compute patron + advanced stats
        patron_stats = await asyncio.to_thread(compute_patron_stats, enriched, diary_df, ratings_df)
        advanced_stats = await asyncio.to_thread(compute_advanced_stats, enriched, diary_df, ratings_df)

        # 7. New feature stats
        community_comparison = await asyncio.to_thread(compute_community_comparison, enriched, ratings_df)
        binge_stats = await asyncio.to_thread(compute_binge_stats, diary_df)
        monthly_activity = await asyncio.to_thread(compute_monthly_activity, enriched, diary_df)
        decade_leaderboard = await asyncio.to_thread(
            compute_decade_leaderboard, enriched, pro_stats.get("_decade_ratings", {})
        )
        pro_stats.pop("_decade_ratings", None)  # internal helper data, not for clients

        result = _json_safe({
            "success": True,
            "stats": {
                "basic": basic_stats,
                "pro": pro_stats,
                "patron": patron_stats,
                "advanced": advanced_stats,
                "community_comparison": community_comparison,
                "binge_stats": binge_stats,
                "monthly_activity": monthly_activity,
                "decade_leaderboard": decade_leaderboard,
            },
            "meta": {
                "total_unique_movies": len(unique_movies),
                "enriched_count": len([m for m in enriched if m.get("tmdb")]),
                "diary_entries": len(diary_df),
                "rated_films": len(ratings_df),
                "watched_films": len(watched_df),
                "lists_count": len(lists_data),
            }
        })

        job["result"] = result
        job["finished_at"] = time.time()
        job["status"] = "done"

    except Exception as e:
        job["status"] = "error"
        # Expected validation errors are safe to show. Hide unexpected internals
        # (paths, implementation details, and exception context) from API clients.
        if isinstance(e, zipfile.BadZipFile):
            job["error"] = BAD_ZIP_MESSAGE
        else:
            job["error"] = str(e) if isinstance(e, ValueError) else GENERIC_FAILURE
        job["finished_at"] = time.time()
        if isinstance(e, (ValueError, zipfile.BadZipFile)):
            logger.warning("Job %s rejected: %s", job_id, (str(e).splitlines() or [type(e).__name__])[0][:200])
        else:
            logger.exception("Job %s failed", job_id)

    finally:
        # Clean up extracted files to prevent disk usage growth
        if extract_path and os.path.isdir(extract_path):
            shutil.rmtree(extract_path, ignore_errors=True)
        await _persist(job_id, job)


# ─── Endpoints ───────────────────────────────────────────────────────────────────────────────────


@router.post("/upload", dependencies=[Depends(_upload_limit)])
async def upload_zip(file: UploadFile = File(...)):
    """
    Upload a Letterboxd export ZIP. Kicks off background processing and returns
    immediately with a job_id and a job_token. Send the token as the
    ``X-Job-Token`` header on every later request for that job.
    """
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".zip"):
        await file.close()
        raise HTTPException(status_code=400, detail="Please upload a .zip file exported from Letterboxd")

    if _active_job_count() >= config.MAX_ACTIVE_JOBS:
        await file.close()
        raise HTTPException(
            status_code=429,
            detail="CineStats is processing other archives. Please try again shortly.",
            headers={"Retry-After": "30"},
        )

    # Read in chunks and always close the upload. Create the job only after
    # validation so oversized uploads cannot leave orphaned idle jobs behind.
    chunks = []
    total_size = 0
    try:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 MB chunks
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > config.MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="CineStats currently supports Letterboxd exports up to 10 MB.",
                )
            chunks.append(chunk)
    finally:
        await file.close()

    contents = b"".join(chunks)
    # Re-check after reading to close the race between simultaneous uploads.
    if _active_job_count() >= config.MAX_ACTIVE_JOBS:
        raise HTTPException(
            status_code=429,
            detail="CineStats is processing other archives. Please try again shortly.",
            headers={"Retry-After": "30"},
        )

    job_id, token, job = _new_job()
    await _persist(job_id, job)
    task = asyncio.create_task(_process_in_background(job_id, contents))
    _background_tasks.add(task)  # hold a reference so the task is not garbage-collected
    task.add_done_callback(_background_tasks.discard)

    return {"success": True, "message": "Processing started", "job_id": job_id, "job_token": token}


@router.get("/progress/{job_id}", dependencies=[Depends(_poll_limit)])
async def get_progress_by_id(authorized: tuple = Depends(_authorized_job)):
    """Get processing progress for a specific job."""
    _, job = authorized
    resp = {
        "status": job["status"],
        "current": job["current"],
        "total": job["total"],
    }
    if job["error"]:
        resp["error"] = job["error"]
    return resp


@router.get("/results/{job_id}", dependencies=[Depends(_poll_limit)])
async def get_results_by_id(authorized: tuple = Depends(_authorized_job)):
    """Fetch final analytics for a specific job."""
    _, job = authorized
    if job["status"] == "done" and job["result"]:
        return job["result"]
    if job["status"] == "error":
        raise HTTPException(status_code=500, detail=job.get("error") or "Processing failed")
    return JSONResponse({"detail": "Still processing"}, status_code=202)


@router.get("/export/pdf/{job_id}", dependencies=[Depends(_export_limit)])
async def export_pdf_by_id(authorized: tuple = Depends(_authorized_job)):
    """Generate and download a CineStats PDF summary for a specific job."""
    _, job = authorized
    if job["status"] != "done" or not job["result"]:
        raise HTTPException(status_code=400, detail="No analysis data available. Upload and process a file first.")

    from app.services.export_service import generate_pdf
    pdf_buffer = await run_in_threadpool(generate_pdf, job["result"])

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=CineStats_Report.pdf"}
    )


@router.delete("/jobs/{job_id}", dependencies=[Depends(_poll_limit)])
async def delete_job(authorized: tuple = Depends(_authorized_job)):
    """Let the uploader erase their analysis immediately instead of waiting for the TTL."""
    job_id, job = authorized
    if job["status"] in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="This analysis is still running. Try again when it finishes.")
    _jobs.pop(job_id, None)
    await job_store.delete(job_id)
    return {"success": True}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
