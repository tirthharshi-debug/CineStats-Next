# CineStats Next

> Your personal cinematheque. A film diary, a record of your taste, and a love letter to the movies that stay with you.

CineStats Next transforms your exported [Letterboxd](https://letterboxd.com/data/export/) `.zip` archive into an editorial film-life dashboard and printable PDF report, enriched with metadata and artwork from TMDB.

---

## Features

* **Editorial Landing & Lazy-Loaded Dashboard:** Warm charcoal-and-ivory UI (`src/App.jsx`) that lazy-loads the analytics dashboard (`src/Dashboard.jsx`) and Recharts bundle only after an analysis completes.
* **Comprehensive Diary & Taste Analytics:**
  * Yearly watching timeline and full 0.5–5.0★ rating distribution
  * Signature genres, genre ratings, and recurring genre pairings
  * Most-watched and highest-rated directors & cast portraits
  * Total runtime (hours/days), 365-day viewing heatmap, and double-feature/binge stats
  * Production countries, spoken languages, monthly poster shelves, and golden decades
  * Crowd vs. personal rating comparisons, rating bias temperament, and latest five-star film reel
* **Top Four Profile Favourites & Share Card:** Parses your Letterboxd `profile.csv` favourites in original order, resolves posters via TMDB, and exports a 1200×1850 PNG share card (`CineStats-Top-Four.png`).
* **Printable PDF Report:** Generates a formatted A4 PDF summary (`CineStats_Report.pdf`) using ReportLab (`backend/app/services/export_service.py`).
* **Screening Queue (Bounded Concurrency):** When all active processing slots (`MAX_ACTIVE_JOBS`) are occupied, additional uploads enter a bounded `"queued"` state (`MAX_QUEUED_JOBS`, up to `QUEUE_WAIT_TIMEOUT_SECONDS`) instead of failing immediately, showing a friendly queue status in the UI. When both active slots and the queue are full, the API returns HTTP `429` with `Retry-After: 30`.
* **Instant Data Deletion ("Delete my data"):** Every completed job can be erased immediately from memory and SQLite via the **Delete my data** button (`DELETE /api/jobs/{job_id}`), or it expires automatically after `JOB_TTL_SECONDS` (default 30 minutes).

### Privacy & Attribution
* **Privacy:** Uploaded ZIP exports are extracted into temporary directories, validated for path traversal/symlinks/size limits, and deleted immediately after parsing (`finally` block in `backend/app/routes/api.py`). Results expire automatically after ~30 minutes (`JOB_TTL_SECONDS=1800`) or immediately via **Delete my data**.
* **TMDB Attribution:** Film metadata, community ratings, cast/director credits, and poster artwork are provided by the [TMDB API](https://www.themoviedb.org). This product uses the TMDB API but is not endorsed or certified by TMDB.
* **Letterboxd:** Letterboxd is a trademark of its owners; CineStats is an independent project and is not affiliated with or endorsed by Letterboxd.

---

## Tech Stack & Architecture

* **Frontend:** React 19, Vite 7, Framer Motion, Recharts, Lucide Icons, Axios (`src/App.jsx`, `src/Dashboard.jsx`, `src/api.js`)
* **Backend:** FastAPI, Uvicorn, Pandas, NumPy, HTTPX, aiosqlite, ReportLab (`backend/app/`)
* **Storage:** SQLite (`jobs.db` for durable job records/tokens, `tmdb_cache.db` for positive & negative TMDB caching)

### Security & Reliability Highlights
* **Per-Job `X-Job-Token` Authorization:** `POST /api/upload` returns a `job_id` (32-char hex) and a `job_token` (`secrets.token_urlsafe(32)`). Only the SHA-256 hash is stored server-side. Every job endpoint (`/api/progress/{job_id}`, `/api/results/{job_id}`, `/api/export/pdf/{job_id}`, `DELETE /api/jobs/{job_id}`) requires `X-Job-Token` and returns an indistinguishable `404` on missing, malformed, or invalid tokens.
* **Shared 30 req/s TMDB Rate Limiter & Cache:** `TMDBService` (`backend/app/services/tmdb_service.py`) uses a module-level, event-loop-aware `asyncio.Semaphore(30)` (`CONCURRENCY = 30`, `RATE_LIMIT_PER_WINDOW = 30` per `1.0s`) shared across all concurrent jobs so aggregate traffic stays safely below TMDB's ~40 req/s ceiling. Matched movies and misses (`TMDB_MISS_TTL_DAYS = 7`) are cached in SQLite.
* **Bounded Upload Queue:** `MAX_ACTIVE_JOBS` (default `2`) + `MAX_QUEUED_JOBS` (default `3`) with `QUEUE_WAIT_TIMEOUT_SECONDS` (default `300`) prevent memory exhaustion while smoothing concurrent upload bursts.
* **Single-Worker Guidance:** Live job progress (`_jobs`), slot conditions (`_slot_conditions`), and per-IP rate limiters (`security.RateLimiter`) are in-memory per process. **Run Uvicorn as a single worker** (1 process) unless backed by an external shared store.
* **Production Hardening:** `APP_ENV=production` disables `/docs` and `/openapi.json`, enables HSTS, enforces `TMDB_API_KEY`/`TMDB_READ_ACCESS_TOKEN` and non-localhost `CORS_ALLOWED_ORIGINS` at startup, and validates `https`-only Letterboxd/boxd.it redirects hop-by-hop when resolving profile favourites.

### Project Structure

```text
CineStats-Next/
├── .env.example                 # Frontend environment template (VITE_API_BASE_URL)
├── .dockerignore                # Root Docker build exclusions
├── index.html                   # HTML entry point & fonts
├── package.json                 # Frontend scripts & dependencies
├── vite.config.js               # Vite build & vendor chunk splitting
├── public/
│   ├── favicon.svg
│   └── images/                  # cinestats-logo.webp, archive-theatre.webp
├── src/
│   ├── main.jsx                 # React root & ErrorBoundary
│   ├── App.jsx                  # Landing page, UploadModal, polling, queue state
│   ├── Dashboard.jsx            # Lazy-loaded analytics dashboard & Top Four share card
│   ├── api.js                   # Axios client with X-Job-Token & AbortSignal support
│   ├── styles.css               # Main editorial stylesheet
│   └── hardening.css            # Fallback brand, TMDB attribution & error boundary styles
└── backend/
    ├── .env.example             # Backend environment template
    ├── .dockerignore
    ├── Dockerfile               # Non-root (appuser) production container
    ├── requirements.txt         # Pinned Python dependencies
    ├── app/
    │   ├── main.py              # FastAPI app, lifespan, CORS, TrustedHost, error handler
    │   ├── config.py            # Environment variable configuration
    │   ├── security.py          # Job tokens, IP rate limiter, security headers, size guard
    │   ├── database/db.py       # SQLite TMDB positive/miss cache
    │   ├── routes/api.py        # Upload, queue, progress, results, PDF export, delete, health
    │   └── services/
    │       ├── file_service.py  # Safe ZIP extraction & Letterboxd CSV parsers
    │       ├── tmdb_service.py  # Shared 30 req/s TMDB client & safe favourite resolution
    │       ├── stats_service.py # Basic, Pro, Patron, Advanced, Community, Monthly, Decade stats
    │       ├── job_store.py     # Durable SQLite job store with TTL purge
    │       └── export_service.py# ReportLab PDF generator
    └── tests/                   # 46 unittest tests (API, security, file service, TMDB)
```

---

## Local Development & Testing

**Prerequisites:** Node.js `>= 20` (Node 22 recommended) and Python `3.11+`.

### 1. Backend Setup

```powershell
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env
```

Edit `backend/.env` and set your TMDB credential (never commit `.env`):
* `TMDB_API_KEY` (v3 key) or `TMDB_READ_ACCESS_TOKEN` (v4 bearer token, recommended)

Start the API server from `backend/`:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive docs are available in development at `http://127.0.0.1:8000/docs`.

### 2. Frontend Setup

In a separate terminal at the repository root:

```powershell
npm install
copy .env.example .env
npm run dev
```

Root `.env.example` sets `VITE_API_BASE_URL=http://localhost:8000/api`.

### 3. Running Tests & Production Build

* **Backend unit tests** (from `backend/`):
  ```powershell
  python -m unittest discover -s tests -v
  ```
* **Backend syntax check** (from repo root):
  ```powershell
  python -m compileall -q backend/app
  ```
* **Frontend production build** (from repo root):
  ```powershell
  npm run build
  ```
* **Frontend dependency audit**:
  ```powershell
  npm run audit:prod
  ```

### Environment Variables Reference

| Variable | Side | Default | Description |
| :--- | :--- | :--- | :--- |
| `VITE_API_BASE_URL` | Frontend | `http://localhost:8000/api` | Public backend API base URL (no secrets). |
| `TMDB_API_KEY` | Backend | *(none)* | TMDB v3 API key (required unless `TMDB_READ_ACCESS_TOKEN` is set). |
| `TMDB_READ_ACCESS_TOKEN` | Backend | *(none)* | TMDB v4 bearer token (preferred; keeps credentials out of URLs). |
| `APP_ENV` | Backend | `development` | Set to `production` on deploy (hides `/docs`, enables HSTS, enforces config). |
| `CORS_ALLOWED_ORIGINS` | Backend | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated exact frontend origins (localhost rejected in production). |
| `ALLOWED_HOSTS` | Backend | *(empty)* | Optional comma-separated `Host` header allowlist (e.g. `cinestats-api.onrender.com`). |
| `DATA_DIR` | Backend | `backend/` (`/data` in Docker) | Directory for `tmdb_cache.db`, `jobs.db`, and temporary `uploads/`. |
| `TRUSTED_PROXY_HOPS` | Backend | `0` | Number of reverse proxies appending to `X-Forwarded-For` (`1` on Render). |
| `MAX_UPLOAD_BYTES` | Backend | `10485760` (10 MB) | Max uploaded `.zip` size. |
| `MAX_ACTIVE_JOBS` | Backend | `2` | Max concurrent jobs actively processing. |
| `MAX_QUEUED_JOBS` | Backend | `3` | Max jobs allowed to wait in `"queued"` state before returning `429`. |
| `QUEUE_WAIT_TIMEOUT_SECONDS` | Backend | `300` | Max seconds a queued job waits for an active slot. |
| `MAX_UNIQUE_MOVIES` | Backend | `6000` | Max unique films allowed per export. |
| `JOB_TTL_SECONDS` | Backend | `1800` | Retention time (seconds) for completed/failed jobs before cleanup. |
| `JOB_CLEANUP_INTERVAL_SECONDS` | Backend | `300` | Interval (seconds) between expired job sweeps. |
| `UPLOADS_PER_HOUR` | Backend | `20` | Per-IP upload rate limit. |
| `POLLS_PER_MINUTE` | Backend | `300` | Per-IP progress/results/delete rate limit. |
| `EXPORTS_PER_MINUTE` | Backend | `10` | Per-IP PDF export rate limit. |
| `TMDB_MISS_TTL_DAYS` | Backend | `7` | Days before retrying an unmatched TMDB title. |
| `LOG_LEVEL` | Backend | `INFO` | Python logging level. |

---

## Deployment Guide (Render + Vercel)

### 1. Deploy Backend on Render
1. Create a new **Web Service** on Render pointing to this repository with **Root Directory** set to `backend` (or using `backend/Dockerfile`).
   * **Build Command** (native Python): `pip install -r requirements.txt`
   * **Start Command** (single worker): `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. *(Optional)* Attach a Render Persistent Disk (e.g., mounted at `/var/data`, or `/data` if using `backend/Dockerfile`) so `tmdb_cache.db` survives deploys.
3. Configure **Environment Variables** on Render:
   * `APP_ENV=production`
   * `TMDB_READ_ACCESS_TOKEN=<your_token>` (or `TMDB_API_KEY=<your_key>`)
   * `CORS_ALLOWED_ORIGINS=https://your-app.vercel.app` (exact origin, no trailing slash)
   * `ALLOWED_HOSTS=your-api.onrender.com`
   * `TRUSTED_PROXY_HOPS=1` (use `2` if proxied through Cloudflare in front of Render)
   * `DATA_DIR=/var/data` (matching your persistent disk mount, if attached)
4. Verify the backend health endpoint:
   ```bash
   curl -i https://your-api.onrender.com/api/health
   # Expected: HTTP 200 {"status":"ok"}
   ```
   Confirm `/docs` returns `404` in production.

### 2. Deploy Frontend on Vercel
1. Import the repository into Vercel (Root Directory: `.`, Framework Preset: **Vite**, Build Command: `npm run build`, Output Directory: `dist`).
2. Add Environment Variable in Vercel Project Settings:
   * `VITE_API_BASE_URL=https://your-api.onrender.com/api`
3. Trigger a deploy (or redeploy after changing `VITE_API_BASE_URL`, since Vite bakes `VITE_*` variables at build time).

### 3. Post-Deploy Smoke Checks
* Open the Vercel URL and verify `/images/cinestats-logo.webp` and `/images/archive-theatre.webp` render cleanly.
* Upload a small Letterboxd `.zip` export and confirm:
  * Progress transitions smoothly through `uploading` → `extracting` → `parsing` → `enriching` → `computing` → `done`.
  * Dashboard renders charts, Top Four (if present in `profile.csv`), and **Print my archive** downloads `CineStats-Your-Film-Life.pdf`.
  * **Delete my data** returns you to the home view and invalidates the job (`GET /api/results/{job_id}` returns `404`).
