"""Phase 1's orchestrator: a single-node LangGraph graph around the
hardcoded worker's task execution, checkpointed to Postgres.

Design rule 2 (orchestration state lives in Postgres, not in a Python
process) starts here even though there's only one step: the checkpointer
persists the graph's state after every node, so a crash mid-run resumes
from Postgres rather than losing progress. Phase 2 adds real branching
(manager -> coder) to this same pattern.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from core.db import AgentORM, TaskORM, session_scope
from workers.hardcoded_worker import execute_task


class Phase1State(TypedDict):
    task_id: str
    run_id: str
    agent_id: str
    status: str


def _make_run_task_node(database_url: str | None) -> Callable[[Phase1State], Phase1State]:
    def _run_task_node(state: Phase1State) -> Phase1State:
        with session_scope(database_url) as session:
            task = session.get(TaskORM, uuid.UUID(state["task_id"]))
            agent = session.get(AgentORM, uuid.UUID(state["agent_id"]))
            assert task is not None
            assert agent is not None
            execute_task(session, task, agent)
            return {**state, "status": task.status}

    return _run_task_node


def build_graph(
    checkpointer: PostgresSaver, *, database_url: str | None = None
) -> CompiledStateGraph[Phase1State]:
    builder = StateGraph(Phase1State)
    builder.add_node("run_task", _make_run_task_node(database_url))  # type: ignore[call-overload]
    builder.set_entry_point("run_task")
    builder.add_edge("run_task", END)
    return builder.compile(checkpointer=checkpointer)


def _as_psycopg_conninfo(sqlalchemy_url: str) -> str:
    """PostgresSaver connects with raw psycopg, which doesn't understand
    SQLAlchemy's `postgresql+psycopg://` driver suffix."""
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


@contextmanager
def get_checkpointer(database_url: str | None = None) -> Iterator[PostgresSaver]:
    url = database_url or os.environ["DATABASE_URL"]
    with PostgresSaver.from_conn_string(_as_psycopg_conninfo(url)) as checkpointer:
        checkpointer.setup()
        yield checkpointer


def run_task_via_graph(
    task_id: uuid.UUID,
    agent_id: uuid.UUID,
    run_id: uuid.UUID,
    *,
    database_url: str | None = None,
) -> str:
    """Execute one task through the checkpointed graph. Returns the task's
    final status."""
    with get_checkpointer(database_url) as checkpointer:
        graph = build_graph(checkpointer, database_url=database_url)
        result = graph.invoke(
            {
                "task_id": str(task_id),
                "run_id": str(run_id),
                "agent_id": str(agent_id),
                "status": "pending",
            },
            config={"configurable": {"thread_id": str(task_id)}},
        )
        status: str = result["status"]
        return status
