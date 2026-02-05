# Table Tennis Fantasy — Frontend (Phase 1)

Minimal Create Team + Team Summary flow. Uses the reference palette: dark background, charcoal cards, lime green primary actions, amber orange accents, rounded corners.

## Run

1. Start the backend from project root:
   ```bash
   uvicorn backend.api:app --reload --port 8000
   ```

2. From this directory:
   ```bash
   npm install
   npm run dev
   ```

3. Open http://localhost:5173 — Create Team page. After submitting, you are redirected to Team Summary.

## API

All requests go through `src/api.ts`. Base URL: `http://127.0.0.1:8000` (override with `VITE_API_BASE` in `.env`). CORS is enabled for `http://localhost:5173` and `http://127.0.0.1:5173`.
