# Dashboard

Phase 1 dashboard: React + Vite + Tailwind + TypeScript.

- **Start a task** — POSTs `/runs`, which creates a run and its one task
  (Phase 1 has no manager agent yet to decompose a goal).
- **Fleet** — polls `/agents` every 2s.
- **Live events** — subscribes to `/runs/{id}/events/stream` (SSE) and
  renders every event as it arrives; it's a read model over that stream
  alone, nothing else (design rule 5).
- **Kill** — POSTs `/tasks/{id}/kill`.

## Running

```bash
npm install
cp .env.example .env.local   # point VITE_API_BASE_URL at your API, if not localhost:8000
npm run dev
```

Requires the API (`api/main.py`) running and reachable at `VITE_API_BASE_URL`.
