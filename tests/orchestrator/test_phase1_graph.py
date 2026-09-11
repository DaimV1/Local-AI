"""Integration test proving the LangGraph + Postgres checkpointer wiring
actually persists and executes (needs real Postgres, see conftest.py)."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import RunORM, TaskORM
from orchestrator.phase1_graph import get_checkpointer, run_task_via_graph
from workers.hardcoded_worker import ensure_agent


def test_run_task_via_graph_executes_and_persists_a_checkpoint(
    pg_session: Session, pg_url: str
) -> None:
    run = RunORM(id=uuid.uuid4(), goal="ship phase 1", workspace_path="/workspaces/run-1")
    pg_session.add(run)
    pg_session.flush()

    task = TaskORM(
        id=uuid.uuid4(),
        run_id=run.id,
        title="write the readme",
        spec={"role": "planner", "instructions": "write a one-line README"},
    )
    pg_session.add(task)
    pg_session.flush()

    agent = ensure_agent(pg_session, name="hardcoded-worker", role="planner", tier="planner")
    pg_session.commit()

    from workers.hardcoded_worker import claim_next_pending_task

    claimed = claim_next_pending_task(pg_session, agent)
    assert claimed is not None
    pg_session.commit()

    status = run_task_via_graph(task.id, agent.id, run.id, database_url=pg_url)

    # The stub-free model call fails (no live LiteLLM in tests), so the
    # graph should still run its node and land the task in "failed" —
    # proving execution flowed through the graph and Postgres, not that
    # a real model answered.
    assert status == "failed"

    pg_session.expire_all()
    refreshed = pg_session.execute(select(TaskORM).where(TaskORM.id == task.id)).scalar_one()
    assert refreshed.status == "failed"

    with get_checkpointer(pg_url) as checkpointer:
        checkpoint = checkpointer.get({"configurable": {"thread_id": str(task.id)}})
        assert checkpoint is not None
