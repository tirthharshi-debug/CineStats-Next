# CineStats Next API

FastAPI backend for Letterboxd export parsing, TMDB metadata enrichment, analytics computation, and PDF report generation.

## Local setup

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
```

Set `TMDB_READ_ACCESS_TOKEN` or `TMDB_API_KEY` in `.env` (never commit it) and `CORS_ALLOWED_ORIGINS` to comma-separated exact frontend origins.

Run from this directory:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs (development only): http://127.0.0.1:8000/docs

## Main workflow

1. Receive the Letterboxd export ZIP and issue a `job_id` + `X-Job-Token` (queued if `MAX_ACTIVE_JOBS` is reached).
2. Reject unsafe ZIP paths, symlink entries, encrypted archives, excessive member counts, and oversized expansions.
3. Parse Letterboxd CSV files and compute basic/pro diary and rating stats.
4. Enrich movie metadata and profile favourites through TMDB with a shared 30 req/s rate limiter and SQLite cache.
5. Compute patron, advanced, community, monthly, and decade analytics.
6. Generate an A4 PDF report on request or delete job data immediately via `DELETE /api/jobs/{job_id}`.

## Current protections

- 10 MB compressed-upload limit, 100 MB expanded-archive limit, 20,000 ZIP members max, and 200,000 CSV rows max.
- Per-job `X-Job-Token` authorization (SHA-256 hashed at rest) on all progress, results, PDF export, and delete endpoints.
- Bounded concurrency (`MAX_ACTIVE_JOBS=2`, `MAX_QUEUED_JOBS=3`) and per-IP sliding-window rate limits.
- Hop-by-hop `https` host validation and 512 KB HTML cap when resolving profile favourite URLs.
- Automatic TTL cleanup (`JOB_TTL_SECONDS=1800`) and single-process in-memory progress tracking (run Uvicorn as a single worker).
