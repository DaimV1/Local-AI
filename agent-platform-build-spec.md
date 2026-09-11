# Build Spec: Local Multi-Agent Platform

You are building a self-hosted multi-agent platform that runs on a single Linux
workstation with a consumer GPU. Read this entire document before writing code.

## How to work on this

- Build **one phase at a time**. Stop at each phase gate, show me what runs, wait for
  go-ahead. Do not scaffold files for future phases.
- If a design rule below conflicts with something you'd rather do, **ask** — don't
  silently substitute. The rules exist for reasons that aren't always local to the file
  you're editing.
- Small commits, conventional commit messages, one concern per commit.
- Every module gets tests. Integration tests over mocks where the thing under test is
  a queue, a DB write, or an event.
- No secrets in the repo. `.env` + `.env.example`.

## What this is

An orchestration layer for 3–20 AI agents working on real tasks against a git
workspace. Roles include a manager/planner, coders, researchers, critics and QC
agents, and the set must be extensible without touching the core.

Models are a commodity here: local models via vLLM/Ollama today, better models in six
months, some roles routed to a hosted API. **Model churn must never require a code
change.**

Target hardware: one Linux box, 24–32 GB VRAM, Postgres and Redis in Docker.
Realistic concurrency on that hardware is 3–6 agents generating at once; the platform
must let 20 agents *exist* and take turns.

## Non-negotiable design rules

1. **Agents never name a model.** An agent declares a capability tier (`planner`,
   `coder`, `researcher`, `judge`, `bulk`). A registry maps tier → model endpoint.
   Changing models is a YAML edit.
2. **Orchestration state lives in Postgres**, not in a Python process. A crash at hour
   three must not lose the run. Every state transition is a committed row.
3. **Agents are workers pulling from a queue**, not function calls. Adding the 20th
   agent is a config number, not a refactor. Workers must be able to run in a separate
   process (and later, a separate machine).
4. **Blackboard over chat.** Agents coordinate through a shared git workspace and the
   `tasks` table. Direct agent-to-agent messaging is allowed only inside a group
   working one subproblem, and is capped.
5. **Everything emits typed events.** The dashboard is a read model over the event
   stream. It never polls an agent or reaches into worker memory.
6. **Budgets are enforced by the orchestrator in code** — max steps, max tokens, max
   wallclock, max revision rounds. A prompt instruction is not a control. Tripping a
   budget escalates to the approval inbox; it does not silently continue.
7. **Structured I/O everywhere.** Pydantic models in and out of every agent. Free prose
   between agents is forbidden except in a designated `notes` field.
8. **Verification is tool-based first.** Critic and QC agents run tests, linters, type
   checkers, schema validators and report structured results. LLM-as-judge is a
   fallback used only where no mechanical check exists, and its verdicts are marked as
   low-confidence in the schema.

## Stack

Pinned. Ask before substituting anything here.

| Layer | Choice |
|---|---|
| Language | Python 3.12, `uv` for deps, `ruff` + `mypy`, `pytest` |
| Orchestrator | LangGraph with Postgres checkpointer |
| Queue / bus | Redis Streams (consumer groups) |
| State | Postgres 16, SQLAlchemy 2.x + Alembic migrations |
| Model gateway | LiteLLM proxy, OpenAI-compatible |
| Inference | vLLM (prod), Ollama (dev) — both behind LiteLLM |
| Isolation | One Docker container per task run, workspace bind-mount |
| Tools | MCP servers, per-role allowlist |
| Tracing | Langfuse via OpenTelemetry |
| API | FastAPI, SSE for the event stream |
| Dashboard | React + Vite + Tailwind, TypeScript |
| Local infra | `docker compose` for Postgres, Redis, LiteLLM, Langfuse |

## Repo layout

```
/core          domain models, event types, budgets, Pydantic schemas
/orchestrator  LangGraph graphs, task decomposition, scheduling, budget enforcement
/workers       base agent worker, role implementations, tool binding
/registry      models.yaml, tier resolution, LiteLLM config generation
/tools         MCP server configs and any custom tool servers
/api           FastAPI app, SSE endpoints, control endpoints
/dashboard     frontend
/migrations    Alembic
/docker        compose files, worker image
/tests
```

## Data model

Design these tables in Phase 1. Add columns as needed; don't remove the concepts.

- **`agents`** — id, name, role, tier, tool_allowlist, status (`idle|working|paused|dead`),
  last_heartbeat, config (jsonb)
- **`runs`** — id, goal, status, created_by, budget (jsonb), started_at, finished_at,
  workspace_path, git_branch
- **`tasks`** — id, run_id, parent_task_id, group_id, title, spec (jsonb), status
  (`pending|claimed|running|blocked|awaiting_approval|done|failed|cancelled`),
  claimed_by, attempt, budget_remaining (jsonb), result (jsonb), created_at, updated_at
- **`events`** — id, run_id, task_id, agent_id, type, payload (jsonb), ts.
  **Append-only. Never update or delete a row here.**
- **`artifacts`** — id, run_id, task_id, kind (`file|diff|report|verdict`), path or
  content_ref, git_sha, created_at
- **`approvals`** — id, run_id, task_id, reason, requested_at, decided_at, decision,
  decided_by, note

Index `events(run_id, ts)` and `tasks(status, claimed_by)` from the start.

## Event taxonomy

A closed enum in `/core`, not free strings. Minimum set:

```
run_started, run_finished, run_cancelled
task_created, task_claimed, task_started, task_blocked, task_completed, task_failed
tool_call_started, tool_call_finished
tokens_used            # tier, prompt, completion, latency_ms
artifact_written       # kind, path, git_sha
verdict_issued         # pass|fail, checks[], confidence, source=tool|llm
budget_warning, budget_exceeded
approval_requested, approval_granted, approval_denied
agent_heartbeat, agent_error
```

Every event carries `run_id`, `ts`, and whichever of `task_id` / `agent_id` applies.
The dashboard must be reconstructable from this stream alone.

## Model registry

`registry/models.yaml` is the only place a model name appears:

```yaml
tiers:
  planner:
    primary: local/qwen3.6-27b
    fallback: api/claude-sonnet
    max_context: 128000
  coder:
    primary: local/qwen3.6-27b
    fallback: api/claude-sonnet
  judge:
    primary: local/gemma4-12b
  bulk:
    primary: local/gemma4-12b
    concurrency_limit: 4

endpoints:
  local/qwen3.6-27b: { provider: openai, api_base: http://litellm:4000, model: qwen3.6-27b }
  ...
```

Generate the LiteLLM proxy config from this file. Write a test that fails if any
string matching a model name appears outside `/registry`.

## Sandboxing and filesystem rules

- Each task run gets a Docker container with **only** `WORKSPACE_PATH` bind-mounted.
  Never the home directory.
- The workspace is a git repo. Agents commit to `agent/<run_id>/<task_id>` branches.
  Nothing writes to `main`.
- Any write outside the workspace, any network egress not on the allowlist, and any
  `git push` require an approval row.
- Container resource limits set explicitly (memory, pids, no privileged mode).

## Phases and acceptance criteria

### Phase 1 — Spine
Docker compose up (Postgres, Redis, LiteLLM, Langfuse). Schema + migrations. Core
Pydantic models and the event enum. Model registry with tier resolution. One
hardcoded worker that claims a task, calls its tier's model, emits events, writes an
artifact. FastAPI with an SSE event stream. Dashboard showing a fleet view and a live
event feed, plus a working kill switch.

**Gate:** I can start a task from the dashboard, watch events arrive in real time, and
kill the agent from the UI. Swapping the planner tier to a different model requires
editing only `models.yaml`.

### Phase 2 — Two agents and a queue
Redis Streams with consumer groups. Base worker class with role subclassing. Manager
agent that decomposes a goal into tasks and writes them to the table; coder agent that
claims and executes them in a sandboxed container against the git workspace. Budget
enforcement wired into the task loop.

**Gate:** A goal produces a task DAG, the coder produces a git branch with real
changes, budgets actually stop runaway loops, and the dashboard renders the DAG with
per-task status.

### Phase 3 — Verification and human gates
Critic/QC worker that runs tools (pytest, ruff, mypy, custom validators) and emits
structured verdicts. Revision loop capped at two rounds, then escalation. Approval
inbox in the dashboard. Git diff viewer.

**Gate:** A failing change is caught by a tool-based check, sent back once, and
escalated to me on second failure. I can approve or reject from the dashboard and the
run continues or stops accordingly.

### Phase 4 — Groups and parallel search
Spawn N isolated variants of a task with different framings, running concurrently
under a shared budget. Intra-group messaging allowed and capped; inter-group silence
enforced. A consolidation step that reads all group outputs and selects or merges.
Scheduler respects per-tier `concurrency_limit` so a 27B tier doesn't oversubscribe
the GPU.

**Gate:** Four variants of one task run in parallel within VRAM limits, and the
consolidator produces one result with a recorded rationale for the selection.

### Phase 5 — Extensibility and hardening
Adding a new specialist agent is a YAML file plus a prompt template — no core changes.
Prove it by adding one. Langfuse traces linked from every task in the dashboard.
Replay: reconstruct any run's dashboard state from the event table alone. Graceful
restart — kill every worker mid-run and have the run resume.

**Gate:** I add a new agent role without touching `/core` or `/orchestrator`, and a
full worker restart mid-run loses no committed work.

## Non-goals

Do not build: multi-tenancy, auth beyond a single local user, Kubernetes, a plugin
marketplace, cloud deployment, fine-tuning or training, a custom tracing UI (Langfuse
covers it), or agent-authored code that modifies this platform's own repo.

## Start here

Confirm you've read this, list anything genuinely ambiguous, then propose the Phase 1
file list and the Postgres schema before writing implementation code.
