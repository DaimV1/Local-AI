from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.models import (
    Agent,
    AgentStatus,
    Budget,
    Run,
    RunStatus,
    Task,
    TaskSpec,
    TaskStatus,
)


def test_agent_round_trips_through_json() -> None:
    agent = Agent(
        id=uuid4(),
        name="coder-1",
        role="coder",
        tier="coder",
        tool_allowlist=["pytest", "ruff"],
        status=AgentStatus.IDLE,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    restored = Agent.model_validate_json(agent.model_dump_json())

    assert restored == agent


def test_run_defaults_to_pending_with_empty_budget() -> None:
    run = Run(id=uuid4(), goal="ship phase 1", workspace_path="/workspaces/run-1")

    assert run.status is RunStatus.PENDING
    assert run.budget == Budget()


def test_task_requires_a_structured_spec_not_free_prose() -> None:
    with pytest.raises(ValidationError):
        Task(
            id=uuid4(),
            run_id=uuid4(),
            title="write the readme",
            spec="just write something good",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )


def test_task_spec_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        TaskSpec(role="coder", instructions="do it", extra_field="not allowed")  # type: ignore[call-arg]


def test_task_defaults_to_pending_status() -> None:
    task = Task(
        id=uuid4(),
        run_id=uuid4(),
        title="write the readme",
        spec=TaskSpec(role="coder", instructions="write README.md"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    assert task.status is TaskStatus.PENDING
    assert task.attempt == 0
