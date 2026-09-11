# Phase 1 Runbook

Everything in this repo was written and tested against a real Postgres in
the build sandbox (its Docker daemon wasn't available there — see
`agent-platform-build-spec.md`'s ambiguity #1), but `docker compose up`
itself has not been run end to end. Run through this on your workstation
and tell me what breaks.

## Prerequisites

- Docker + Docker Compose v2, GPU drivers set up
- [Ollama](https://ollama.com) installed and running natively (not in
  Docker) so it has direct GPU access
- `uv` (https://docs.astral.sh/uv/), Python 3.12
- Node 22+ (only needed if you want to run the dashboard outside Docker)

## 1. Configure

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, LITELLM_MASTER_KEY, and (optional)
# ANTHROPIC_API_KEY if you want the fallback tier to work
```

`registry/models.yaml` ships with the exact model identifiers from the
build spec's own example (`qwen3.6-27b`, `gemma4-12b`). Pull whatever you
actually have:

```bash
ollama pull <your-planner/coder-model>
ollama pull <your-judge/bulk-model>
```

If your tags differ, edit `registry/models.yaml`'s `endpoints.*.backend.model`
to match — that's the only file a model name should ever appear in (a test
enforces this).

## 2. Generate the LiteLLM proxy config

```bash
uv sync
uv run python -m registry.generate_litellm_config
```

Re-run this any time `models.yaml` changes — it's gitignored, not
committed.

## 3. Bring up the stack

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

This starts Postgres, Redis, LiteLLM, Langfuse, the API (which runs
`alembic upgrade head` on boot), the worker, and the dashboard.

Langfuse is pinned to `langfuse/langfuse:2` (needs only Postgres, unlike
v3's ClickHouse + object storage requirement) — I could not verify this
against Langfuse's current docs from the build sandbox (network egress to
langfuse.com is blocked there). If it doesn't come up cleanly, that
container is the one to look at first; nothing else in the stack depends
on it for Phase 1.

Check everything is healthy:

```bash
docker compose -f docker/docker-compose.yml ps
```

## 4. Run the gate

1. Open http://localhost:5173
2. Fill in a goal + instructions, click **Start**
3. Watch events arrive live in the **Live events** panel
   (`run_started` → `task_created` → `task_claimed` → `task_started` →
   `tokens_used` → `artifact_written` → `task_completed`, or
   `task_failed` if the model call errors)
4. Watch the **Fleet** panel's `hardcoded-worker` status flip
   idle → working → idle as it processes the task
5. Start another run and click **Kill** while its task is still pending —
   it should flip to `cancelled` immediately; a second click 409s

## 5. Prove the model registry works

```bash
# edit registry/models.yaml: change tiers.planner.primary to point at a
# different endpoint (or a different backend.model on the same endpoint)
uv run python -m registry.generate_litellm_config
docker compose -f docker/docker-compose.yml restart litellm worker
```

Start a new run — it should use the new model, with zero code changes.

## Troubleshooting

- **Task always fails immediately with a connection error**: the worker
  can't reach LiteLLM, or LiteLLM can't reach Ollama. Check
  `docker compose logs litellm` and confirm Ollama is listening on
  `localhost:11434` on the host (the compose file adds
  `host.docker.internal` for containers to reach it).
- **`alembic upgrade head` fails on api container start**: check
  `docker compose logs api` — likely Postgres wasn't ready yet despite the
  healthcheck, or `DATABASE_URL` in `.env` doesn't match what you set for
  `POSTGRES_*`.
- **Dashboard shows a CORS error in the console**: shouldn't happen (CORS
  is wide open in `api/main.py` for this single-local-user Phase 1), but
  if it does, confirm `VITE_API_BASE_URL` in the dashboard's env actually
  points at the API's real host:port.

## Running tests locally (outside Docker)

The suite skips every integration test if Postgres isn't reachable. To
run them for real:

```bash
# a local Postgres, or `docker compose -f docker/docker-compose.yml up -d postgres`
export TEST_DATABASE_URL="postgresql+psycopg://local_ai:change-me@localhost:5432/local_ai_test"
uv run pytest
```

For the dashboard:

```bash
cd dashboard && npm run lint && npm run build
```
