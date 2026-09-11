"""Domain models shared by the orchestrator, workers, and API.

These are the Pydantic schemas required by design rule 7 ("structured I/O
everywhere"): every value that crosses an agent boundary is one of these
models, never free-form prose (the `notes` fields are the sole exception).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Role and tier are plain strings, not enums: design rule 1 requires that
# adding a new tier or role (Phase 5) is a YAML edit, never a change to
# /core.
Role = str
Tier = str


class AgentStatus(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    PAUSED = "paused"
    DEAD = "dead"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    BLOCKED = "blocked"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactKind(StrEnum):
    FILE = "file"
    DIFF = "diff"
    REPORT = "report"
    VERDICT = "verdict"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class Budget(BaseModel):
    """Enforced by the orchestrator in code (design rule 6), never a prompt
    instruction. Used both as a run's limits (`runs.budget`) and as a
    task's remaining allowance (`tasks.budget_remaining`)."""

    model_config = ConfigDict(extra="forbid")

    max_steps: int | None = None
    max_tokens: int | None = None
    max_wallclock_seconds: int | None = None
    max_revision_rounds: int | None = None


class TaskSpec(BaseModel):
    """What a worker needs to execute a task. `notes` is the one field
    allowed to carry free prose (design rule 7)."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    instructions: str
    context: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class TaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    artifact_ids: list[UUID] = Field(default_factory=list)
    notes: str | None = None


class Agent(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    role: Role
    tier: Tier
    tool_allowlist: list[str] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.IDLE
    last_heartbeat: datetime | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class Run(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    goal: str
    status: RunStatus = RunStatus.PENDING
    created_by: str = "local-user"
    budget: Budget = Field(default_factory=Budget)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    workspace_path: str
    git_branch: str | None = None


class Task(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    parent_task_id: UUID | None = None
    group_id: UUID | None = None
    title: str
    spec: TaskSpec
    status: TaskStatus = TaskStatus.PENDING
    claimed_by: UUID | None = None
    attempt: int = 0
    budget_remaining: Budget = Field(default_factory=Budget)
    result: TaskResult | None = None
    created_at: datetime
    updated_at: datetime


class Artifact(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    task_id: UUID | None = None
    kind: ArtifactKind
    path: str | None = None
    content_ref: str | None = None
    git_sha: str | None = None
    created_at: datetime


class Approval(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    task_id: UUID | None = None
    reason: str
    requested_at: datetime
    decided_at: datetime | None = None
    decision: ApprovalDecision | None = None
    decided_by: str | None = None
    note: str | None = None
