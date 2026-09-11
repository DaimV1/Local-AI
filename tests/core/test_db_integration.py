"""Integration tests against a real Postgres (skipped if unreachable).

Run `docker compose up -d postgres` first (see RUNBOOK.md), then
`uv run pytest tests/core/test_db_integration.py`.
"""

import uuid

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from core.db import AgentORM, EventORM, RunORM, TaskORM


def test_writing_a_run_task_and_event_round_trips(pg_session: Session) -> None:
    run = RunORM(id=uuid.uuid4(), goal="ship phase 1", workspace_path="/workspaces/run-1")
    pg_session.add(run)
    pg_session.flush()

    agent = AgentORM(id=uuid.uuid4(), name="coder-1", role="coder", tier="coder")
    pg_session.add(agent)
    pg_session.flush()

    task = TaskORM(
        id=uuid.uuid4(),
        run_id=run.id,
        title="write the readme",
        spec={"role": "coder", "instructions": "write README.md"},
        claimed_by=agent.id,
        status="claimed",
    )
    pg_session.add(task)
    pg_session.flush()

    event = EventORM(
        id=uuid.uuid4(),
        run_id=run.id,
        task_id=task.id,
        agent_id=agent.id,
        type="task_claimed",
        payload={},
    )
    pg_session.add(event)
    pg_session.flush()

    stored = pg_session.get(EventORM, event.id)
    assert stored is not None
    assert stored.seq > 0
    assert stored.type == "task_claimed"


def test_events_table_rejects_updates(pg_session: Session) -> None:
    run = RunORM(id=uuid.uuid4(), goal="ship phase 1", workspace_path="/workspaces/run-1")
    pg_session.add(run)
    pg_session.flush()

    event = EventORM(id=uuid.uuid4(), run_id=run.id, type="run_started", payload={})
    pg_session.add(event)
    pg_session.flush()

    event.type = "run_finished"
    with pytest.raises(DBAPIError, match="append-only"):
        pg_session.flush()


def test_events_table_rejects_deletes(pg_session: Session) -> None:
    run = RunORM(id=uuid.uuid4(), goal="ship phase 1", workspace_path="/workspaces/run-1")
    pg_session.add(run)
    pg_session.flush()

    event = EventORM(id=uuid.uuid4(), run_id=run.id, type="run_started", payload={})
    pg_session.add(event)
    pg_session.flush()

    pg_session.delete(event)
    with pytest.raises(DBAPIError, match="append-only"):
        pg_session.flush()


def test_task_status_check_constraint_rejects_unknown_status(pg_session: Session) -> None:
    run = RunORM(id=uuid.uuid4(), goal="ship phase 1", workspace_path="/workspaces/run-1")
    pg_session.add(run)
    pg_session.flush()

    task = TaskORM(
        id=uuid.uuid4(),
        run_id=run.id,
        title="write the readme",
        spec={"role": "coder", "instructions": "write README.md"},
        status="not-a-real-status",
    )
    pg_session.add(task)
    with pytest.raises(DBAPIError):
        pg_session.flush()
