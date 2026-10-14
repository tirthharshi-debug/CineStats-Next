# CineStats Next API

This directory contains an isolated copy of the existing CineStats FastAPI backend, with an initial set of safety hardening changes.

## Local setup

Python 3.11+ recommended.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
```

Set `TMDB_API_KEY` in `.env`. Keep the key server-side and never commit it. Set `CORS_ALLOWED_ORIGINS` to comma-separated exact frontend origins.

Run from this directory:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs: http://127.0.0.1:8000/docs

## Main workflow

1. Receive the Letterboxd export ZIP.
2. Reject unsafe ZIP paths, symlink entries, excessive member counts and archives expanding past the configured size limit.
3. Parse Letterboxd CSV files and compute basic diary/rating stats.
4. Enrich movie metadata through TMDB and cache it in SQLite.
5. Compute analytics and make results available to the frontend.
6. Generate a PDF report on request.

## Current protections

- 10 MB compressed-upload limit.
- 100 MB expanded-archive limit and a maximum of 20,000 ZIP members.
- Unique temporary extraction directories and cleanup on failure.
- ZIP path traversal and symlink rejection.
- Maximum of two simultaneous active analyses per process.
- CORS defaults to local Vite origins and can be configured with `CORS_ALLOWED_ORIGINS`.
- Unexpected processing exceptions are logged server-side while clients receive a generic message.

## Remaining production work

The in-memory job dictionary still does not survive process restarts or share state between instances. Add durable job storage/queueing, per-user job ownership or signed job access, per-IP upload throttling, better observability, end-to-end tests, and deployment-specific storage settings before treating this as a public multi-user service. SQLite caching is rebuildable; do not rely on an ephemeral host filesystem for long-term persistence.
