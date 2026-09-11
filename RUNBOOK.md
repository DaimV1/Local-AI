# Phase 1 Runbook

Everything Python/TypeScript in this repo was written and tested against
a real Postgres and a real headless-browser dashboard session in the
build sandbox. `docker compose up` itself has not been run end to end:
the sandbox's Docker daemon can start, but its network policy blocks
pulling images from Docker Hub / GHCR (confirmed via the proxy's own
status endpoint — a policy-denied 403, not a transient failure). Run
through this on your workstation and tell me what breaks.

## Prerequisites

- Docker + Docker Compose v2, GPU drivers set up
- [Ollama](https://ollama.com) installed and running natively (not in
  Docker) so it has direct GPU access
- `uv` (https://docs.astral.sh/uv/), Python 3.12
- Node 22+ (only needed if you want to run the dashboard outside Docker)
- `openssl` (for generating Langfuse's secrets below — it ships with
  every Linux/macOS install)

## 1. Configure

```bash
cp .env.example .env
```

Edit `.env`:

- `POSTGRES_PASSWORD`, `LITELLM_MASTER_KEY` — pick anything
- `ANTHROPIC_API_KEY` — optional, only needed for the fallback tier
- `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, `LANGFUSE_ENCRYPTION_KEY` —
  three **distinct** values, each `openssl rand -hex 32` (`ENCRYPTION_KEY`
  specifically must be 64 hex chars; compose refuses to start Langfuse if
  any of the three is left as the placeholder)

Every `docker compose` command below needs `--env-file .env` — compose's
automatic `.env` discovery looks next to the compose file
(`docker/docker-compose.yml`), not the repo root where you just created
it. Easiest to just alias it once per shell:

```bash
alias dc="docker compose --env-file .env -f docker/docker-compose.yml"
```

(All commands below assume this alias and that you're running them from
the repo root.)

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
dc up -d --build
```

This starts Postgres, Redis, LiteLLM, Langfuse, the API (which runs
`alembic upgrade head` on boot), the worker, and the dashboard.

Langfuse is pinned to `langfuse/langfuse:2`, which needs only Postgres
(v3 additionally wants ClickHouse and S3-compatible object storage). I
checked this against `langfuse/langfuse`'s own v2 `docker-compose.yml` on
GitHub and matched its required env vars (`DATABASE_URL`, `NEXTAUTH_URL`,
`NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY`) — but I still haven't run it,
so treat first boot as the real test. Revisit the v2 pin when Phase 5
wires real trace linking.

Check everything is healthy:

```bash
dc ps
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
dc restart litellm worker
```

Start a new run — it should use the new model, with zero code changes.

## Troubleshooting

- **Langfuse container won't start / complains about a missing var**:
  double check `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`, and
  `LANGFUSE_ENCRYPTION_KEY` are all set to distinct real values in `.env`,
  not left as `change-me` — compose enforces this and will refuse to
  start the service otherwise, naming which one is missing.
- **Task always fails immediately with a connection error**: the worker
  can't reach LiteLLM, or LiteLLM can't reach Ollama. Check
  `dc logs litellm` and confirm Ollama is listening on `localhost:11434`
  on the host (the compose file adds `host.docker.internal` for
  containers to reach it).
- **`alembic upgrade head` fails on api container start**: check
  `dc logs api` — likely Postgres wasn't ready yet despite the
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
# a local Postgres, or `dc up -d postgres`
export TEST_DATABASE_URL="postgresql+psycopg://local_ai:change-me@localhost:5432/local_ai_test"
uv run pytest
```

For the dashboard:

```bash
cd dashboard && npm run lint && npm run build
```
