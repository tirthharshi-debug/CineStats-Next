# CineStats Next 🎞️

> Your personal cinematheque. A film diary, a record of your taste, and a love letter to the movies that stay with you.

CineStats Next is a new, cinema-first evolution of CineStats. Its visual direction takes cues from repertory cinema programmes, independent film journals, archival catalogues and beautifully printed festival guides.

## Design principles

- **Cinema first:** film-inspired artwork, editorial typography and thoughtful curation come before charts.
- **A personal archive:** stats should reveal viewing habits, taste and memories, not reduce cinema to counts.
- **Warm, tactile visual language:** near-black charcoal, warm ivory, film-red accents and restrained brass.
- **Honest data:** no invented viewing statistics or demo results presented as a user's real diary.
- **Preserve the engine:** reuse the existing analytics backend where it is sound, while improving production concerns deliberately.

## Current implementation

- Responsive cinematic landing page with poster-inspired artwork.
- Letterboxd export import dialog with drag-and-drop, file extension and 10 MB size checks.
- Real upload, per-job progress polling, result retrieval, and PDF export API calls.
- Overview metrics using actual API payload data.
- Viewing-year and rating-distribution charts, plus first/most recent diary entry and rewatch summaries.
- Configurable API URL using `VITE_API_BASE_URL`.
- GitHub Actions workflow that installs dependencies and verifies the Vite production build on pushes and pull requests.

## API configuration

For now, the default API points to the original CineStats hosted backend as a compatibility bridge:

```env
VITE_API_BASE_URL=https://letterboxd-stats-vuaq.onrender.com/api
```

Copy `.env.example` to `.env` and change this value when a dedicated CineStats Next backend is deployed. Do not put TMDB API keys or other secrets in frontend environment variables.

The new interface currently surfaces an initial selection of the existing API's analytics. More of the original Patron/advanced analytics, poster-led diary views and richer personal insights still need to be ported and verified.

## Local development

Requirements: Node.js 20+ (Node 22 recommended) and npm.

```bash
npm install
npm run dev
```

Create a production build:

```bash
npm run build
npm run preview
```

## Roadmap

1. Port the rest of the existing analytics into the new interface without fabricating data.
2. Add poster-led diary browsing, filters, director/genre/country/language details and richer personal insights.
3. Improve upload and job reliability, resource limits, CORS and service monitoring in the backend.
4. Add automated tests for import validation, polling, result rendering and PDF download.
5. Deploy the frontend and its dedicated backend separately from the original CineStats application.

## Status

Early build — the first frontend production build passes in GitHub Actions. This is not yet a complete feature-for-feature replacement for the original deployment.

Original project: https://github.com/tirthharshi-debug/CineStats

## Attribution

CineStats Next is an independent personal project for exploring a Letterboxd export. Letterboxd and TMDB are trademarks of their respective owners. This project is not affiliated with or endorsed by Letterboxd or TMDB.
