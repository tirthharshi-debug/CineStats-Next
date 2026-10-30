# CineStats Next 🎞️

> Your personal cinematheque. A film diary, a record of your taste, and a love letter to the movies that stay with you.

CineStats Next is a cinema-first evolution of CineStats, taking visual cues from repertory cinema programmes, independent film journals, archival catalogues and beautifully printed festival guides. The original CineStats repository and live deployment remain separate.

## The current build

- Editorial landing page with warm ivory typography, charcoal backgrounds, film-red accents and restrained brass details.
- Poster-inspired artwork made from CSS rather than fake user data.
- Letterboxd ZIP import with file checks, upload progress, processing status and error states.
- API client for upload, per-job progress, results and PDF export.
- Data-backed sections for yearly/rating charts, genres, director and actor credits, runtime, watch calendar, monthly poster shelves, decade leaderboards, country/language patterns, crowd-rating comparisons and rating insights.
- Isolated copy of the existing FastAPI/TMDB/SQLite/PDF backend with initial upload, ZIP and CORS hardening.
- GitHub Actions checks for the React production build and Python backend tests/syntax.
- Configurable upload-job admission limit (`CINESTATS_MAX_ACCEPTED_JOBS`, default `6` per backend process); increase only after load testing the target host.

## Stack

- **Frontend:** React, Vite, Framer Motion, Recharts, Lucide
- **Backend:** FastAPI, Pandas, SQLite/aiosqlite, TMDB API, ReportLab
- **Data source:** Your Letterboxd export ZIP, enriched via TMDB

## Local full-stack setup

Requirements: Node.js 20+ (Node 22 recommended), npm, and Python 3.11+.

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
```

Add a server-side `TMDB_API_KEY` to `backend/.env`. Never commit it.

Run from the `backend` directory:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

### 2. Frontend

In another terminal, from the repository root:

```bash
npm install
copy .env.example .env
npm run dev
```

Open the local URL printed by Vite. The root `.env.example` points to `http://localhost:8000/api`. For a deployed frontend, set `VITE_API_BASE_URL` to the deployed backend URL and redeploy.

## Backend concurrency tuning

Set `CINESTATS_MAX_ACCEPTED_JOBS` in `backend/.env` or your backend hosting environment to change how many uploads are accepted for processing at once **per backend process**. The default is `6`. You can lower or raise it with this setting; `CINESTATS_MAX_ACCEPTED_JOBS=6` allows up to six accepted jobs in one process. Requests above the limit receive HTTP 429 and can retry shortly.

This is not a global limit across multiple worker processes or hosting instances. Raising it increases simultaneous memory, CPU and TMDB usage; validate with realistic exports and slow API responses before raising it in production. The in-memory job registry also means multi-worker deployments are not yet safe for reliable job polling.

## Current production-readiness boundary

CineStats Next is an early, separate build—not a feature-for-feature production replacement yet. The copied backend now guards ZIP extraction and upload concurrency, and its CORS policy is configurable, but job state is still in memory and does not survive restarts or span instances. Before public multi-user deployment, add durable jobs, job ownership/access control, per-IP throttling, end-to-end tests and deployment-specific storage configuration. Do not treat the SQLite cache on an ephemeral host as permanent storage.

## Attribution

CineStats Next is an independent project for exploring a Letterboxd export. Letterboxd and TMDB belong to their respective owners. This project is not affiliated with or endorsed by Letterboxd or TMDB.

Original project: https://github.com/tirthharshi-debug/CineStats
