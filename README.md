# CineStats Next 🎞️

> Your personal cinematheque. A film diary, a record of your taste, and a love letter to the movies that stay with you.

CineStats Next is a cinema-first evolution of CineStats, taking visual cues from repertory cinema programmes, independent film journals, archival catalogues and beautifully printed festival guides. The original CineStats repository and live deployment remain separate.

## The current build

- Editorial landing page with warm ivory typography, charcoal backgrounds, film-red accents and brass details.
- Poster-inspired artwork made from CSS rather than fake user data.
- Letterboxd ZIP import dialog with drag-and-drop, upload progress, processing status and clear error states.
- API client for upload, per-job progress, result retrieval and PDF export.
- An initial data-backed analytics screen with viewing-year and rating charts, plus first/most recent diary entries and rewatches.
- GitHub Actions workflow to install dependencies and verify the Vite production build.

The current screen intentionally surfaces only an initial subset of the original API's analytics. More advanced genre, director, actor, country, language, runtime, monthly, decade and community views remain on the roadmap.

## Stack

- **Frontend:** React, Vite, Framer Motion, Recharts, Lucide
- **Backend:** FastAPI, Pandas, SQLite/aiosqlite, TMDB API
- **Data source:** Your own Letterboxd export ZIP, enriched via TMDB

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

Edit `backend/.env` and add a real server-side `TMDB_API_KEY`. Never commit it.

Start the API from inside the `backend` directory:

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

Open the local URL printed by Vite. The root `.env.example` points the frontend to `http://localhost:8000/api`. For a deployed frontend, set `VITE_API_BASE_URL` to the deployed backend URL and redeploy.

## API endpoints currently used

- `POST /api/upload`
- `GET /api/progress/{job_id}`
- `GET /api/results/{job_id}`
- `GET /api/export/pdf/{job_id}`

## Important production work still required

The backend is an isolated copy of the existing baseline, not yet the final hardened release. Before public deployment, address the in-memory job queue (restart/multi-instance behavior), CORS origin policy, expanded ZIP/resource limits, job ownership/isolation, error handling and automated backend tests. The SQLite cache is for metadata; do not store Letterboxd exports or secrets in the repository. Render's ephemeral filesystem considerations must be reviewed before relying on cache persistence.

## Roadmap

1. Harden the copied backend and add focused tests.
2. Port the rest of the existing analytics to the new cinematic UI without fabricating data.
3. Add poster-led diary browsing, genre/director/actor/country/language details, richer personal insights and refined PDF output.
4. Configure independent frontend/backend deployments and secrets.

## Attribution

CineStats Next is an independent project for exploring a Letterboxd export. Letterboxd and TMDB belong to their respective owners. This project is not affiliated with or endorsed by Letterboxd or TMDB.

Original project: https://github.com/tirthharshi-debug/CineStats
