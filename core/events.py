"""The closed event taxonomy (design rule 5).

The dashboard is a read model over this stream and nothing else — it never
polls an agent or reaches into worker memory. `EventType` is a closed enum,
never a free string, and every member has a typed payload model registered
in `EVENT_PAYLOAD_TYPES` so the stream can be validated end to end.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_CANCELLED = "run_cancelled"

    TASK_CREATED = "task_created"
    TASK_CLAIMED = "task_claimed"
    TASK_STARTED = "task_started"
    TASK_BLOCKED = "task_blocked"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_FINISHED = "tool_call_finished"

    TOKENS_USED = "tokens_used"
    ARTIFACT_WRITTEN = "artifact_written"
    VERDICT_ISSUED = "verdict_issued"

    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"

    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"

    AGENT_HEARTBEAT = "agent_heartbeat"
    AGENT_ERROR = "agent_error"


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunStartedPayload(_Payload):
    goal: str


class RunFinishedPayload(_Payload):
    status: Literal["completed", "failed"]


class RunCancelledPayload(_Payload):
    reason: str


class TaskCreatedPayload(_Payload):
    title: str


class TaskClaimedPayload(_Payload):
    pass


class TaskStartedPayload(_Payload):
    pass


class TaskBlockedPayload(_Payload):
    reason: str


class TaskCompletedPayload(_Payload):
    summary: str


class TaskFailedPayload(_Payload):
    error: str


class ToolCallStartedPayload(_Payload):
    tool: str


class ToolCallFinishedPayload(_Payload):
    tool: str
    ok: bool


class TokensUsedPayload(_Payload):
    tier: str
    prompt: int
    completion: int
    latency_ms: int


class ArtifactWrittenPayload(_Payload):
    kind: Literal["file", "diff", "report", "verdict"]
    path: str | None = None
    git_sha: str | None = None


class VerdictIssuedPayload(_Payload):
    status: Literal["pass", "fail"]
    checks: list[str] = Field(default_factory=list)
    confidence: float
    source: Literal["tool", "llm"]


class BudgetWarningPayload(_Payload):
    dimension: Literal["steps", "tokens", "wallclock_seconds", "revision_rounds"]
    used: float
    limit: float


class BudgetExceededPayload(_Payload):
    dimension: Literal["steps", "tokens", "wallclock_seconds", "revision_rounds"]
    used: float
    limit: float


class ApprovalRequestedPayload(_Payload):
    approval_id: UUID
    reason: str


class ApprovalGrantedPayload(_Payload):
    approval_id: UUID
    decided_by: str


class ApprovalDeniedPayload(_Payload):
    approval_id: UUID
    decided_by: str


class AgentHeartbeatPayload(_Payload):
    status: Literal["idle", "working", "paused", "dead"]


class AgentErrorPayload(_Payload):
    error: str


EVENT_PAYLOAD_TYPES: dict[EventType, type[_Payload]] = {
    EventType.RUN_STARTED: RunStartedPayload,
    EventType.RUN_FINISHED: RunFinishedPayload,
    EventType.RUN_CANCELLED: RunCancelledPayload,
    EventType.TASK_CREATED: TaskCreatedPayload,
    EventType.TASK_CLAIMED: TaskClaimedPayload,
    EventType.TASK_STARTED: TaskStartedPayload,
    EventType.TASK_BLOCKED: TaskBlockedPayload,
    EventType.TASK_COMPLETED: TaskCompletedPayload,
    EventType.TASK_FAILED: TaskFailedPayload,
    EventType.TOOL_CALL_STARTED: ToolCallStartedPayload,
    EventType.TOOL_CALL_FINISHED: ToolCallFinishedPayload,
    EventType.TOKENS_USED: TokensUsedPayload,
    EventType.ARTIFACT_WRITTEN: ArtifactWrittenPayload,
    EventType.VERDICT_ISSUED: VerdictIssuedPayload,
    EventType.BUDGET_WARNING: BudgetWarningPayload,
    EventType.BUDGET_EXCEEDED: BudgetExceededPayload,
    EventType.APPROVAL_REQUESTED: ApprovalRequestedPayload,
    EventType.APPROVAL_GRANTED: ApprovalGrantedPayload,
    EventType.APPROVAL_DENIED: ApprovalDeniedPayload,
    EventType.AGENT_HEARTBEAT: AgentHeartbeatPayload,
    EventType.AGENT_ERROR: AgentErrorPayload,
}


class Event(BaseModel):
    """Envelope stored in the append-only `events` table."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seq: int
    run_id: UUID
    task_id: UUID | None = None
    agent_id: UUID | None = None
    type: EventType
    payload: dict[str, object] = Field(default_factory=dict)
    ts: datetime

    def parsed_payload(self) -> _Payload:
        """Validate `payload` against the model registered for `type`."""
        return EVENT_PAYLOAD_TYPES[self.type].model_validate(self.payload)
