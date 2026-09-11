"""Phase 1's single hardcoded worker.

Claims one pending task, calls its tier's model, emits typed events at
every transition, writes an artifact, and honors cooperative cancellation
(the Phase 1 kill switch: the API flips the task to `cancelled` and this
worker notices at its next checkpoint — there's no per-task container to
signal yet, that arrives with Phase 2 sandboxing).
"""

from __future__ import annotations

import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import (
    AgentORM,
    ApprovalORM,
    ArtifactORM,
    RunORM,
    TaskORM,
    record_event,
    session_scope,
)
from core.events import (
    AgentHeartbeatPayload,
    ApprovalRequestedPayload,
    ArtifactWrittenPayload,
    BudgetExceededPayload,
    EventType,
    TaskClaimedPayload,
    TaskCompletedPayload,
    TaskFailedPayload,
    TaskStartedPayload,
    TokensUsedPayload,
)
from orchestrator.budgets import check_budget
from registry.resolver import DEFAULT_REGISTRY_PATH, resolve_tier
from workers.model_caller import LiteLLMCaller, ModelCaller

POLL_INTERVAL_SECONDS = 2.0


def ensure_agent(session: Session, *, name: str, role: str, tier: str) -> AgentORM:
    agent = session.execute(select(AgentORM).where(AgentORM.name == name)).scalar_one_or_none()
    if agent is not None:
        return agent

    agent = AgentORM(id=uuid.uuid4(), name=name, role=role, tier=tier, status="idle")
    session.add(agent)
    session.flush()
    return agent


def claim_next_pending_task(session: Session, agent: AgentORM) -> TaskORM | None:
    task = session.execute(
        select(TaskORM)
        .where(TaskORM.status == "pending")
        .order_by(TaskORM.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if task is None:
        return None

    task.status = "claimed"
    task.claimed_by = agent.id
    agent.status = "working"
    session.flush()

    record_event(
        session,
        run_id=task.run_id,
        task_id=task.id,
        agent_id=agent.id,
        event_type=EventType.TASK_CLAIMED,
        payload=TaskClaimedPayload(),
    )
    return task


def _is_cancelled(session: Session, task_id: uuid.UUID) -> bool:
    session.expire_all()
    status = session.execute(select(TaskORM.status).where(TaskORM.id == task_id)).scalar_one()
    return status == "cancelled"


def _pause_for_cancellation(session: Session, task: TaskORM, agent: AgentORM) -> None:
    agent.status = "paused"
    session.flush()
    record_event(
        session,
        run_id=task.run_id,
        task_id=task.id,
        agent_id=agent.id,
        event_type=EventType.AGENT_HEARTBEAT,
        payload=AgentHeartbeatPayload(status="paused"),
    )


def execute_task(
    session: Session,
    task: TaskORM,
    agent: AgentORM,
    *,
    model_caller: ModelCaller | None = None,
    registry_path: str = str(DEFAULT_REGISTRY_PATH),
) -> None:
    model_caller = model_caller or LiteLLMCaller()

    run = session.get(RunORM, task.run_id)
    assert run is not None

    if _is_cancelled(session, task.id):
        _pause_for_cancellation(session, task, agent)
        return

    violation = check_budget(run, task)
    if violation is not None:
        reason = f"budget exceeded: {violation.dimension} ({violation.used} > {violation.limit})"
        approval = ApprovalORM(id=uuid.uuid4(), run_id=run.id, task_id=task.id, reason=reason)
        session.add(approval)
        task.status = "awaiting_approval"
        agent.status = "idle"
        session.flush()
        record_event(
            session,
            run_id=run.id,
            task_id=task.id,
            agent_id=agent.id,
            event_type=EventType.BUDGET_EXCEEDED,
            payload=BudgetExceededPayload(
                dimension=violation.dimension, used=violation.used, limit=violation.limit
            ),
        )
        record_event(
            session,
            run_id=run.id,
            task_id=task.id,
            agent_id=agent.id,
            event_type=EventType.APPROVAL_REQUESTED,
            payload=ApprovalRequestedPayload(approval_id=approval.id, reason=reason),
        )
        return

    task.status = "running"
    session.flush()
    record_event(
        session,
        run_id=run.id,
        task_id=task.id,
        agent_id=agent.id,
        event_type=EventType.TASK_STARTED,
        payload=TaskStartedPayload(),
    )

    resolved = resolve_tier(agent.tier, registry_path)

    try:
        response = model_caller(resolved.primary, task.spec["instructions"])
    except Exception as exc:  # the model call is the one step that can fail
        task.status = "failed"
        agent.status = "idle"
        session.flush()
        record_event(
            session,
            run_id=run.id,
            task_id=task.id,
            agent_id=agent.id,
            event_type=EventType.TASK_FAILED,
            payload=TaskFailedPayload(error=str(exc)),
        )
        return

    record_event(
        session,
        run_id=run.id,
        task_id=task.id,
        agent_id=agent.id,
        event_type=EventType.TOKENS_USED,
        payload=TokensUsedPayload(
            tier=agent.tier,
            prompt=response.prompt_tokens,
            completion=response.completion_tokens,
            latency_ms=response.latency_ms,
        ),
    )

    if _is_cancelled(session, task.id):
        _pause_for_cancellation(session, task, agent)
        return

    artifact_path = f"{run.workspace_path}/{task.id}.md"
    artifact = ArtifactORM(
        id=uuid.uuid4(), run_id=run.id, task_id=task.id, kind="file", path=artifact_path
    )
    session.add(artifact)
    session.flush()
    record_event(
        session,
        run_id=run.id,
        task_id=task.id,
        agent_id=agent.id,
        event_type=EventType.ARTIFACT_WRITTEN,
        payload=ArtifactWrittenPayload(kind="file", path=artifact_path),
    )

    task.status = "done"
    task.result = {"summary": response.text[:500], "artifact_ids": [str(artifact.id)]}
    agent.status = "idle"
    session.flush()
    record_event(
        session,
        run_id=run.id,
        task_id=task.id,
        agent_id=agent.id,
        event_type=EventType.TASK_COMPLETED,
        payload=TaskCompletedPayload(summary=response.text[:500]),
    )


def run_once(*, database_url: str | None = None, model_caller: ModelCaller | None = None) -> bool:
    """Claim and execute a single pending task, if any. Returns whether it
    found work to do."""
    with session_scope(database_url) as session:
        agent = ensure_agent(session, name="hardcoded-worker", role="planner", tier="planner")
        task = claim_next_pending_task(session, agent)
        if task is None:
            return False
        execute_task(session, task, agent, model_caller=model_caller)
        return True


def main() -> None:
    print("hardcoded-worker: polling for tasks (Ctrl+C to stop)")
    while True:
        did_work = run_once()
        if not did_work:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
