# CineStats-Next 🎞️

Letterboxd export analytics web app. Upload a Letterboxd `.zip` export, enrich film metadata via TMDB, explore interactive diary/rating/genre/director analytics, export a PNG Top Four share card or PDF report, and delete your data on demand.

## ✨ What It Does

* **📊 Diary & Rating Analytics:** Yearly watch history, 0.5–5.0★ rating distribution, genres and pairings, director/cast frequencies, total runtime, 365-day activity heatmap, binge days, monthly shelves, golden decades, crowd-rating diffs, and latest five-star films.
* **🎬 Profile Top Four:** Parses `profile.csv` favourites in original order, resolves posters via TMDB, and renders a 1200×1850 PNG share card client-side.
* **📄 PDF Export:** Generates an A4 summary report (`ReportLab`) off the event loop.
* **⏳ Bounded Upload Queue:** Active jobs (`MAX_ACTIVE_JOBS=2`) run concurrently; additional uploads enter a bounded `"queued"` state (`MAX_QUEUED_JOBS=3`, `QUEUE_WAIT_TIMEOUT_SECONDS=300`) instead of failing immediately, returning `429` (`Retry-After: 30`) only when both active slots and the queue are full.
* **🗑️ Job Isolation & Deletion:** Each upload receives a 32-hex `job_id` and a `secrets.token_urlsafe(32)` `X-Job-Token` (stored as SHA-256). Jobs expire after `JOB_TTL_SECONDS` (`1800`s) or can be deleted immediately via **Delete my data** (`DELETE /api/jobs/{job_id}`).

## 🛠️ Stack & Architecture

* **Frontend:** React 19, Vite 7, Framer Motion, Recharts, Lucide, Axios (`src/`). The dashboard (`src/Dashboard.jsx`) and Recharts bundle are lazy-loaded after an analysis finishes.
* **Backend:** FastAPI, Uvicorn, Pandas, NumPy, HTTPX, aiosqlite, ReportLab (`backend/app/`).
* **Persistence:** SQLite (`jobs.db` for durable job records/tokens; `tmdb_cache.db` for positive TMDB cache and 7-day miss cache).
* **TMDB Rate Limiting:** `TMDBService` enforces a module-level, event-loop-aware `30 req/s` shared limit (`CONCURRENCY=30`, `RATE_LIMIT_PER_WINDOW=30`) across all active jobs.
* **Input & Network Guards:** ZIP extraction checks member count (`20,000`), expanded size (`100 MB`), per-CSV size (`40 MB`), row count (`200,000`), path traversal, symlinks, and encryption, and deletes temp directories in `finally`. Profile favourite URLs are capped at 4 and resolved with `https`-only, hop-by-hop host-validated redirects and a 512 KB HTML limit.
* **Single-Worker Note:** Live job progress, queue conditions, and per-IP rate limiters (`RateLimiter`) live in process memory. Run Uvicorn as a single worker process.

## 📁 Project Layout

```text
├── .env.example              # Frontend env template (VITE_API_BASE_URL)
├── package.json              # Vite & React scripts
├── vite.config.js            # Build config & vendor chunking
├── public/images/            # cinestats-logo.webp, archive-theatre.webp
├── src/
│   ├── App.jsx               # Landing view, UploadModal, polling & queue state
│   ├── Dashboard.jsx         # Lazy-loaded analytics dashboard & Top Four PNG export
│   ├── api.js                # Axios client (X-Job-Token, AbortSignal, Retry-After)
│   ├── main.jsx              # Root & ErrorBoundary
│   └── styles.css            # Styles (+ hardening.css)
└── backend/
    ├── .env.example          # Backend env template
    ├── Dockerfile            # Non-root container (appuser, DATA_DIR=/data)
    ├── requirements.txt      # Pinned Python dependencies
    ├── app/
    │   ├── main.py           # FastAPI app, lifespan, CORS, TrustedHost, error handler
    │   ├── config.py         # Env config
    │   ├── security.py       # Job tokens, IP rate limiter, security headers, size limit
    │   ├── database/db.py    # SQLite TMDB cache
    │   ├── routes/api.py     # /api/upload, /progress, /results, /export/pdf, /jobs, /health
    │   └── services/         # file_service, tmdb_service, stats_service, job_store, export_service
    └── tests/                # unittest suite
```

## 🔐 Environment Variables

Copy `.env.example` to `.env` (frontend) and `backend/.env.example` to `backend/.env` (backend). Never commit `.env` files.

* **Frontend (`.env.example`):** `VITE_API_BASE_URL` (default `http://localhost:8000/api`)
* **Backend (`backend/.env.example`):**
  * `TMDB_READ_ACCESS_TOKEN` (v4 bearer token, preferred) or `TMDB_API_KEY` (v3 key)
  * `APP_ENV` (`development` | `production`; `production` hides `/docs` & `/openapi.json`, enables HSTS, and validates config on startup)
  * `CORS_ALLOWED_ORIGINS` (comma-separated exact origins, no trailing slash)
  * `ALLOWED_HOSTS` (optional comma-separated `Host` allowlist)
  * `TRUSTED_PROXY_HOPS` (`0` locally; set to proxy hop count behind a reverse proxy)
  * `DATA_DIR` (directory for SQLite DBs and temp `uploads/`; defaults to `backend/`, `/data` in Docker)
  * Tuning defaults: `MAX_UPLOAD_BYTES=10485760`, `MAX_ACTIVE_JOBS=2`, `MAX_QUEUED_JOBS=3`, `QUEUE_WAIT_TIMEOUT_SECONDS=300`, `MAX_UNIQUE_MOVIES=6000`, `JOB_TTL_SECONDS=1800`, `UPLOADS_PER_HOUR=20`, `POLLS_PER_MINUTE=300`, `EXPORTS_PER_MINUTE=10`, `TMDB_MISS_TTL_DAYS=7`

## 🚀 Local Setup

Requires Node.js `>= 20` and Python `3.11+`.

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # set TMDB_READ_ACCESS_TOKEN or TMDB_API_KEY
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
npm install
copy .env.example .env
npm run dev
```

## 🧪 Tests & Build

```powershell
# Backend unit tests (from backend/)
python -m unittest discover -s tests -v

# Backend syntax check (from repo root)
python -m compileall -q backend/app

# Frontend production build & dependency audit (from repo root)
npm run build
npm run audit:prod
```

---

Film metadata and poster images are provided by the [TMDB API](https://www.themoviedb.org). This product uses the TMDB API but is not endorsed or certified by TMDB. CineStats-Next is an independent project and is not affiliated with Letterboxd.
