"""
API routes for the Letterboxd analytics application.
Uses background processing with per-job state to support multiple simultaneous users.
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import asyncio
import traceback
import os
import shutil
import uuid
import time

from app.services.file_service import (
    extract_zip, validate_letterboxd_export,
    parse_diary, parse_ratings, parse_watched,
    parse_watchlist, parse_lists, get_unique_movies
)
from app.services.tmdb_service import TMDBService
from app.services.stats_service import (
    compute_basic_stats, compute_pro_stats,
    compute_patron_stats, compute_advanced_stats,
    compute_community_comparison, compute_binge_stats,
    compute_monthly_activity, compute_decade_leaderboard
)
from app.services.cache_service import stats as cache_stats

router = APIRouter()

# ─── Per-job state for background processing ───
# Each job_id maps to its own state dict, enabling multiple simultaneous users.
_jobs: dict[str, dict] = {}

# Cleanup settings
_CLEANUP_INTERVAL = 600   # 10 minutes
_JOB_TTL = 1800           # 30 minutes after completion
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def _new_job() -> tuple[str, dict]:
    """Create a new job with a unique ID and return (job_id, job_state)."""
    job_id = uuid.uuid4().hex
    job = {
        "status": "idle",        # idle | extracting | parsing | enriching | computing | done | error
        "current": 0,
        "total": 0,
        "result": None,
        "error": None,
        "basic_stats": None,     # Available early (before TMDB)
        "pro_stats": None,       # Available early (before TMDB)
        "created_at": time.time(),
        "finished_at": None,
    }
    _jobs[job_id] = job
    return job_id, job


def _get_job(job_id: str) -> dict:
    """Look up a job by ID, raising 404 if not found."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _latest_job() -> dict | None:
    """Return the most recently created job, or None."""
    if not _jobs:
        return None
    return _jobs[max(_jobs, key=lambda k: _jobs[k]["created_at"])]


async def _cleanup_old_jobs():
    """Periodically remove completed/errored jobs older than _JOB_TTL."""
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        now = time.time()
        expired = [
            jid for jid, job in _jobs.items()
            if job["status"] in ("done", "error")
            and job.get("finished_at")
            and (now - job["finished_at"]) > _JOB_TTL
        ]
        for jid in expired:
            _jobs.pop(jid, None)
        if expired:
            print(f"[Cleanup] Evicted {len(expired)} old job(s)")


# Start the cleanup loop when this module is first imported by FastAPI
_cleanup_task: asyncio.Task | None = None


def _ensure_cleanup_started():
    """Start the cleanup background task if not already running."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_old_jobs())


async def _process_in_background(job_id: str, file_bytes: bytes):
    """Run the full pipeline in the background for a specific job."""
    job = _jobs[job_id]
    extract_path = None
    try:
        job["status"] = "extracting"

        # 1. Extract ZIP
        extract_path = extract_zip(file_bytes)

        # Validate before parsing — fail fast on non-Letterboxd ZIPs
        validate_letterboxd_export(extract_path)

        job["status"] = "parsing"

        # 2. Parse CSVs
        diary_df = parse_diary(extract_path)
        ratings_df = parse_ratings(extract_path)
        watched_df = parse_watched(extract_path)
        watchlist_df = parse_watchlist(extract_path)
        lists_data = parse_lists(extract_path)

        # 3. Compute basic + pro stats immediately (no TMDB needed)
        basic_stats = compute_basic_stats(diary_df, ratings_df, watched_df)
        pro_stats = compute_pro_stats(diary_df, ratings_df)

        # Make these available for early display while TMDB enrichment runs
        job["basic_stats"] = basic_stats
        job["pro_stats"] = pro_stats

        # 4. Get unique movies for TMDB enrichment
        unique_movies = get_unique_movies(diary_df, watched_df, ratings_df)
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
        patron_stats = compute_patron_stats(enriched, diary_df, ratings_df)
        advanced_stats = compute_advanced_stats(enriched, diary_df, ratings_df)

        # 7. New feature stats
        community_comparison = compute_community_comparison(enriched, ratings_df)
        binge_stats = compute_binge_stats(diary_df)
        monthly_activity = compute_monthly_activity(enriched, diary_df)
        decade_leaderboard = compute_decade_leaderboard(
            enriched, pro_stats.get("_decade_ratings", {})
        )

        job["status"] = "done"
        job["finished_at"] = time.time()
        job["result"] = {
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
        }

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["finished_at"] = time.time()
        traceback.print_exc()

    finally:
        # Clean up extracted files to prevent disk usage growth
        if extract_path and os.path.isdir(extract_path):
            shutil.rmtree(extract_path, ignore_errors=True)


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/upload")
async def upload_zip(file: UploadFile = File(...)):
    """
    Upload a Letterboxd export ZIP. Kicks off background processing
    and returns immediately with a job_id. Poll /progress/{job_id} for status.
    """
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Please upload a .zip file")

    job_id, job = _new_job()

    # SEC-02: Read in chunks to reject oversized uploads without exhausting memory
    chunks = []
    total_size = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB chunks
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=(
                    "\ud83c\udfac That's a director's cut we can't handle.\n\n"
                    "CineStats currently supports Letterboxd exports up to 10 MB."
                ),
            )
        chunks.append(chunk)
    contents = b"".join(chunks)

    # Ensure the cleanup loop is running
    _ensure_cleanup_started()

    # Fire and forget — runs in the background
    asyncio.create_task(_process_in_background(job_id, contents))

    return {"success": True, "message": "Processing started", "job_id": job_id}


@router.get("/progress/{job_id}")
async def get_progress_by_id(job_id: str):
    """Get processing progress for a specific job."""
    job = _get_job(job_id)
    resp = {
        "status": job["status"],
        "current": job["current"],
        "total": job["total"],
    }
    if job["error"]:
        resp["error"] = job["error"]
    if job["basic_stats"]:
        resp["basic_stats"] = job["basic_stats"]
    if job["pro_stats"]:
        resp["pro_stats"] = job["pro_stats"]
    return resp


@router.get("/results/{job_id}")
async def get_results_by_id(job_id: str):
    """Fetch final analytics for a specific job."""
    job = _get_job(job_id)
    if job["status"] == "done" and job["result"]:
        return job["result"]
    elif job["status"] == "error":
        raise HTTPException(status_code=500, detail=job.get("error", "Processing failed"))
    else:
        raise HTTPException(status_code=202, detail="Still processing")


@router.get("/export/pdf/{job_id}")
async def export_pdf_by_id(job_id: str):
    """Generate and download a CineStats PDF summary for a specific job."""
    job = _get_job(job_id)
    if job["status"] != "done" or not job["result"]:
        raise HTTPException(status_code=400, detail="No analysis data available. Upload and process a file first.")

    from app.services.export_service import generate_pdf
    pdf_buffer = generate_pdf(job["result"])

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=CineStats_Report.pdf"}
    )


# ─── Backward-compatible shim endpoints (no job_id) ─────────────────────────
# These find the most recent job so the app works even without frontend changes.


@router.get("/progress")
async def get_progress():
    """Get progress for the most recent job (backward compat)."""
    job = _latest_job()
    if not job:
        return {"status": "idle", "current": 0, "total": 0}
    resp = {
        "status": job["status"],
        "current": job["current"],
        "total": job["total"],
    }
    if job["error"]:
        resp["error"] = job["error"]
    if job["basic_stats"]:
        resp["basic_stats"] = job["basic_stats"]
    if job["pro_stats"]:
        resp["pro_stats"] = job["pro_stats"]
    return resp


@router.get("/results")
async def get_results():
    """Fetch results for the most recent job (backward compat)."""
    job = _latest_job()
    if not job:
        raise HTTPException(status_code=400, detail="No processing has been started")
    if job["status"] == "done" and job["result"]:
        return job["result"]
    elif job["status"] == "error":
        raise HTTPException(status_code=500, detail=job.get("error", "Processing failed"))
    else:
        raise HTTPException(status_code=202, detail="Still processing")


@router.get("/export/pdf")
async def export_pdf():
    """Generate PDF for the most recent job (backward compat)."""
    job = _latest_job()
    if not job or job["status"] != "done" or not job["result"]:
        raise HTTPException(status_code=400, detail="No analysis data available. Upload and process a file first.")

    from app.services.export_service import generate_pdf
    pdf_buffer = generate_pdf(job["result"])

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=CineStats_Report.pdf"}
    )


@router.get("/cache-stats")
async def get_cache_stats():
    """Get TMDB cache statistics."""
    return await cache_stats()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
