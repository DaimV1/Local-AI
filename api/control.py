"""Control endpoints: start a run and kill a task.

Phase 1 has no manager agent to decompose a goal yet (that's Phase 2), so
starting a run here creates its one task directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from api.deps import get_db
from core.db import AgentORM, RunORM, TaskORM, record_event
from core.events import EventType, RunStartedPayload, TaskCreatedPayload
from core.models import Agent, Budget, Run, Task, TaskSpec

router = APIRouter()

TERMINAL_TASK_STATUSES = {"done", "failed", "cancelled"}


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    instructions: str
    workspace_path: str = "/workspaces/default"
    budget: Budget = Field(default_factory=Budget)


class CreateRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: Run
    task: Task


@router.post("/runs", response_model=CreateRunResponse)
def create_run(body: CreateRunRequest, session: Session = Depends(get_db)) -> CreateRunResponse:
    run = RunORM(
        id=uuid.uuid4(),
        goal=body.goal,
        status="running",
        budget=body.budget.model_dump(),
        started_at=datetime.now(UTC),
        workspace_path=body.workspace_path,
    )
    session.add(run)
    session.flush()
    record_event(
        session,
        run_id=run.id,
        event_type=EventType.RUN_STARTED,
        payload=RunStartedPayload(goal=body.goal),
    )

    task_spec = TaskSpec(role="planner", instructions=body.instructions)
    task = TaskORM(
        id=uuid.uuid4(),
        run_id=run.id,
        title=body.goal,
        spec=task_spec.model_dump(mode="json"),
        status="pending",
    )
    session.add(task)
    session.flush()
    record_event(
        session,
        run_id=run.id,
        task_id=task.id,
        event_type=EventType.TASK_CREATED,
        payload=TaskCreatedPayload(title=task.title),
    )

    return CreateRunResponse(run=Run.model_validate(run), task=Task.model_validate(task))


@router.post("/tasks/{task_id}/kill", response_model=Task)
def kill_task(task_id: uuid.UUID, session: Session = Depends(get_db)) -> Task:
    """The Phase 1 kill switch: flip the task to `cancelled`. The worker
    notices cooperatively at its next checkpoint and pauses its agent —
    there's no per-task container to signal directly until Phase 2."""
    task = session.get(TaskORM, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status in TERMINAL_TASK_STATUSES:
        raise HTTPException(status_code=409, detail=f"task already {task.status}")

    task.status = "cancelled"
    session.flush()
    return Task.model_validate(task)


@router.get("/agents", response_model=list[Agent])
def list_agents(session: Session = Depends(get_db)) -> list[Agent]:
    agents = session.query(AgentORM).order_by(AgentORM.name).all()
    return [Agent.model_validate(a) for a in agents]


@router.get("/runs/{run_id}", response_model=Run)
def get_run(run_id: uuid.UUID, session: Session = Depends(get_db)) -> Run:
    run = session.get(RunORM, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return Run.model_validate(run)


@router.get("/runs/{run_id}/tasks", response_model=list[Task])
def list_run_tasks(run_id: uuid.UUID, session: Session = Depends(get_db)) -> list[Task]:
    tasks = (
        session.query(TaskORM).filter(TaskORM.run_id == run_id).order_by(TaskORM.created_at).all()
    )
    return [Task.model_validate(t) for t in tasks]
