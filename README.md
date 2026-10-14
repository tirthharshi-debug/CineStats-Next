# CineStats Next 🎞️

> Your personal cinematheque. A film diary, a record of your taste, and a love letter to the movies that stay with you.

CineStats Next is a ground-up evolution of CineStats, built for cinephiles rather than generic dashboard users. The design direction takes cues from repertory cinema programmes, independent film journals, archival catalogues and beautifully printed festival guides.

## Design principles

- **Cinema first:** film art, editorial typography and thoughtful curation come before charts.
- **A personal archive:** stats should reveal viewing habits, taste and memories, not reduce cinema to counts.
- **Warm, tactile visual language:** near-black charcoal, warm ivory, film-strip red and restrained brass.
- **Honest data:** no invented viewing statistics, fake AI insights, or demo results presented as a user's real diary.
- **Preserve the engine:** retain and integrate the existing Letterboxd/TMDB analytics backend where it is sound, improving production concerns in deliberate steps.

## Roadmap

1. Build the cinema-first design system and responsive interface.
2. Add an accessible, welcoming Letterboxd export import flow with real upload/progress/error states.
3. Integrate real API results: viewing diary, ratings, genres, people, time, release eras and personal insights.
4. Bring in poster-led curation, diary timeline, archive filters and share/export flows.
5. Harden backend job management, upload/resource limits, CORS, security, tests and deployment docs.

## Project structure

The first commit establishes the frontend foundation. Backend integration will be added after the UI shell and API contracts are clearly established.

## Local development

Requirements: Node.js 20+ and npm.

```bash
npm install
npm run dev
```

## Status

Early build — frontend foundation. Not yet a connected replacement for the original CineStats deployment.

Original project: https://github.com/tirthharshi-debug/CineStats

## Attribution

CineStats Next is an independent personal project for exploring a Letterboxd export. Letterboxd and TMDB are trademarks of their respective owners. This is not affiliated with or endorsed by Letterboxd or TMDB.
