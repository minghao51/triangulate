# Frontend

This directory contains the React frontend for browsing persisted cases and operator outputs against the read-only Triangulate HTTP API.

## Stack

- React 19
- TypeScript
- Vite
- React Router

## Scripts

```bash
npm install
npm run dev
npm run build
npm run lint
npm run preview
```

## API Integration

- The client reads `VITE_API_BASE_URL` to locate the backend.
- API helpers live in `src/services/api.ts`.
- Shared backend-facing types live in `src/types/backend-models.ts`.
- The frontend must not initiate pipeline mutations; operators use the CLI or background workers for that.

## Current Routes

- `/`: case index
- `/cases/new`: CLI launch guidance
- `/cases/:id/*`: case detail views

## Notes

- This is no longer a stock Vite template; keep this README focused on project-specific behavior.
- Remove template-only assets and references when they are not used by the app.
