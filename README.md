# Local AI

A self-hosted multi-agent orchestration platform for a single Linux
workstation with a consumer GPU. See `agent-platform-build-spec.md` for
the full design (non-negotiable rules, stack, phases, data model), and
`RUNBOOK.md` for exact steps to bring up Phase 1 on your workstation.

## Status: Phase 1 — Spine

Docker compose stack (Postgres, Redis, LiteLLM, Langfuse, API, worker,
dashboard), the six-table schema, the closed event taxonomy, the
tier→model registry, one hardcoded worker running behind a checkpointed
LangGraph graph, and a dashboard with a fleet view, a live event feed,
and a kill switch.

## Repo layout

```
/core          domain models, event types, budgets, Pydantic schemas
/orchestrator  LangGraph graphs, budget enforcement
/workers       base agent worker, role implementations
/registry      models.yaml, tier resolution, LiteLLM config generation
/api           FastAPI app, SSE endpoint, control endpoints
/dashboard     frontend (React + Vite + Tailwind)
/migrations    Alembic
/docker        compose files, Dockerfiles
/tests         mirrors the layout above
```

## Quick start

See `RUNBOOK.md`.
