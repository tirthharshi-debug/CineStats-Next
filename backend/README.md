# CineStats Next API

This directory contains the initial isolated copy of the existing CineStats FastAPI backend.

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

Set `TMDB_API_KEY` in `.env`. Keep the key server-side and never commit it.

Run from this directory:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs: http://127.0.0.1:8000/docs

## Main workflow

1. Receive the Letterboxd export ZIP.
2. Validate the archive and extract expected CSVs.
3. Compute immediate diary/rating stats.
4. Enrich movie metadata with TMDB and cache it in SQLite.
5. Compute analytics and make results available to the frontend.
6. Generate a PDF report on request.

## Baseline status

This is a starting point copied from the original application so CineStats Next can be developed independently. It is not yet production-hardened. The current in-memory job dictionary does not survive process restarts and does not share state between instances; CORS is permissive; resource limits for expanded ZIP contents and background concurrency need improvement; tests and deployment-specific storage decisions are still required.

Do not deploy this baseline as a public service until those concerns are resolved.
