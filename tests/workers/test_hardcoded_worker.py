"""Integration tests for the Phase 1 hardcoded worker.

Needs a real Postgres (skipped otherwise, see tests/conftest.py). Never
calls a real model: model_caller is always a stub here so the suite
doesn't depend on Ollama/LiteLLM being up.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import ApprovalORM, ArtifactORM, EventORM, RunORM, TaskORM
from registry.resolver import EndpointConfig
from workers.hardcoded_worker import claim_next_pending_task, ensure_agent, execute_task
from workers.model_caller import ModelResponse


class StubModelCaller:
    def __init__(
        self,
        *,
        text: str = "here is the readme",
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
        latency_ms: int = 42,
        exc: Exception | None = None,
    ) -> None:
        self.text = text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.latency_ms = latency_ms
        self.exc = exc
        self.calls: list[tuple[EndpointConfig, str]] = []

    def __call__(self, endpoint: EndpointConfig, prompt: str) -> ModelResponse:
        self.calls.append((endpoint, prompt))
        if self.exc is not None:
            raise self.exc
        return ModelResponse(
            text=self.text,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            latency_ms=self.latency_ms,
        )


def _make_run(session: Session, **overrides: object) -> RunORM:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "goal": "ship phase 1",
        "workspace_path": "/workspaces/run-1",
    }
    run = RunORM(**{**defaults, **overrides})
    session.add(run)
    session.flush()
    return run


def _make_task(session: Session, run: RunORM, **overrides: object) -> TaskORM:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "run_id": run.id,
        "title": "write the readme",
        "spec": {"role": "planner", "instructions": "write a one-line README"},
    }
    task = TaskORM(**{**defaults, **overrides})
    session.add(task)
    session.flush()
    return task


def _events_for(session: Session, task_id: uuid.UUID) -> list[EventORM]:
    return list(
        session.execute(
            select(EventORM).where(EventORM.task_id == task_id).order_by(EventORM.seq)
        ).scalars()
    )


def test_happy_path_claims_calls_model_writes_artifact_and_completes(
    pg_session: Session,
) -> None:
    run = _make_run(pg_session)
    task = _make_task(pg_session, run)
    agent = ensure_agent(pg_session, name="hardcoded-worker", role="planner", tier="planner")

    claimed = claim_next_pending_task(pg_session, agent)
    assert claimed is not None
    assert claimed.id == task.id

    stub = StubModelCaller(text="# README\n")
    execute_task(pg_session, claimed, agent, model_caller=stub)

    pg_session.refresh(claimed)
    pg_session.refresh(agent)
    assert claimed.status == "done"
    assert claimed.result is not None
    assert claimed.result["summary"] == "# README\n"
    assert agent.status == "idle"
    assert len(stub.calls) == 1

    artifact = pg_session.execute(
        select(ArtifactORM).where(ArtifactORM.task_id == task.id)
    ).scalar_one()
    assert artifact.path == f"{run.workspace_path}/{task.id}.md"

    event_types = [e.type for e in _events_for(pg_session, task.id)]
    assert event_types == [
        "task_claimed",
        "task_started",
        "tokens_used",
        "artifact_written",
        "task_completed",
    ]


def test_budget_exceeded_requests_approval_without_calling_the_model(
    pg_session: Session,
) -> None:
    run = _make_run(
        pg_session,
        budget={"max_wallclock_seconds": 1},
        started_at=datetime.now(UTC) - timedelta(seconds=60),
    )
    task = _make_task(pg_session, run)
    agent = ensure_agent(pg_session, name="hardcoded-worker", role="planner", tier="planner")
    claimed = claim_next_pending_task(pg_session, agent)
    assert claimed is not None

    stub = StubModelCaller()
    execute_task(pg_session, claimed, agent, model_caller=stub)

    pg_session.refresh(claimed)
    pg_session.refresh(agent)
    assert claimed.status == "awaiting_approval"
    assert agent.status == "idle"
    assert stub.calls == []

    approval = pg_session.execute(
        select(ApprovalORM).where(ApprovalORM.task_id == task.id)
    ).scalar_one()
    assert "wallclock_seconds" in approval.reason

    event_types = [e.type for e in _events_for(pg_session, task.id)]
    assert event_types == ["task_claimed", "budget_exceeded", "approval_requested"]


def test_cancellation_between_claim_and_execution_pauses_the_agent(
    pg_session: Session,
) -> None:
    run = _make_run(pg_session)
    task = _make_task(pg_session, run)
    agent = ensure_agent(pg_session, name="hardcoded-worker", role="planner", tier="planner")
    claimed = claim_next_pending_task(pg_session, agent)
    assert claimed is not None

    # Simulate the kill switch: the control API flips the task to cancelled
    # out from under the worker.
    claimed.status = "cancelled"
    pg_session.flush()

    stub = StubModelCaller()
    execute_task(pg_session, claimed, agent, model_caller=stub)

    pg_session.refresh(agent)
    pg_session.refresh(claimed)
    assert claimed.status == "cancelled"
    assert agent.status == "paused"
    assert stub.calls == []

    event_types = [e.type for e in _events_for(pg_session, task.id)]
    assert event_types == ["task_claimed", "agent_heartbeat"]


def test_model_failure_marks_the_task_failed(pg_session: Session) -> None:
    run = _make_run(pg_session)
    task = _make_task(pg_session, run)
    agent = ensure_agent(pg_session, name="hardcoded-worker", role="planner", tier="planner")
    claimed = claim_next_pending_task(pg_session, agent)
    assert claimed is not None

    stub = StubModelCaller(exc=RuntimeError("litellm proxy unreachable"))
    execute_task(pg_session, claimed, agent, model_caller=stub)

    pg_session.refresh(claimed)
    pg_session.refresh(agent)
    assert claimed.status == "failed"
    assert agent.status == "idle"

    artifacts = pg_session.execute(
        select(ArtifactORM).where(ArtifactORM.task_id == task.id)
    ).scalars().all()
    assert artifacts == []

    event_types = [e.type for e in _events_for(pg_session, task.id)]
    assert event_types == ["task_claimed", "task_started", "task_failed"]
