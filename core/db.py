"""SQLAlchemy engine, session, and ORM tables for the Phase 1 schema.

Design rule 2: orchestration state lives in Postgres, not in a Python
process — every state transition here is a committed row, not an in-memory
value.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from core.events import EVENT_PAYLOAD_TYPES, EventType

load_dotenv()


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _fk_uuid(target: str, *, nullable: bool = True) -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), ForeignKey(target), nullable=nullable)


def _timestamp(*, server_default_now: bool = False) -> Mapped[datetime]:
    kwargs: dict[str, Any] = {"server_default": func.now()} if server_default_now else {}
    return mapped_column(TIMESTAMP(timezone=True), **kwargs)


class AgentORM(Base):
    __tablename__ = "agents"
    __table_args__ = (
        CheckConstraint("status IN ('idle','working','paused','dead')", name="ck_agents_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)
    tool_allowlist: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="idle")
    last_heartbeat: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = _timestamp(server_default_now=True)
    updated_at: Mapped[datetime] = _timestamp(server_default_now=True)


class RunORM(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="local-user")
    budget: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    git_branch: Mapped[str | None] = mapped_column(Text)


class TaskORM(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','claimed','running','blocked',"
            "'awaiting_approval','done','failed','cancelled')",
            name="ck_tasks_status",
        ),
        Index("ix_tasks_status_claimed_by", "status", "claimed_by"),
        Index("ix_tasks_run_id", "run_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = _fk_uuid("runs.id", nullable=False)
    parent_task_id: Mapped[uuid.UUID | None] = _fk_uuid("tasks.id")
    group_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    claimed_by: Mapped[uuid.UUID | None] = _fk_uuid("agents.id")
    attempt: Mapped[int] = mapped_column(default=0)
    budget_remaining: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _timestamp(server_default_now=True)
    updated_at: Mapped[datetime] = _timestamp(server_default_now=True)


class EventORM(Base):
    """Append-only. Rows are never updated or deleted — enforced by a
    trigger installed in migrations/versions/0001_initial_schema.py."""

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_run_id_ts", "run_id", "ts"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    run_id: Mapped[uuid.UUID] = _fk_uuid("runs.id", nullable=False)
    task_id: Mapped[uuid.UUID | None] = _fk_uuid("tasks.id")
    agent_id: Mapped[uuid.UUID | None] = _fk_uuid("agents.id")
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    ts: Mapped[datetime] = _timestamp(server_default_now=True)


class ArtifactORM(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("kind IN ('file','diff','report','verdict')", name="ck_artifacts_kind"),
        CheckConstraint("path IS NOT NULL OR content_ref IS NOT NULL", name="ck_artifacts_ref"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = _fk_uuid("runs.id", nullable=False)
    task_id: Mapped[uuid.UUID | None] = _fk_uuid("tasks.id")
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str | None] = mapped_column(Text)
    content_ref: Mapped[str | None] = mapped_column(Text)
    git_sha: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _timestamp(server_default_now=True)


class ApprovalORM(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("decision IN ('approved','rejected')", name="ck_approvals_decision"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = _fk_uuid("runs.id", nullable=False)
    task_id: Mapped[uuid.UUID | None] = _fk_uuid("tasks.id")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_at: Mapped[datetime] = _timestamp(server_default_now=True)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    decision: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(database_url: str | None = None) -> Engine:
    global _engine
    if _engine is None:
        url = database_url or os.environ["DATABASE_URL"]
        _engine = create_engine(url, future=True)
    return _engine


def get_sessionmaker(database_url: str | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(database_url), expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope(database_url: str | None = None) -> Generator[Session, None, None]:
    session = get_sessionmaker(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def record_event(
    session: Session,
    *,
    run_id: uuid.UUID,
    event_type: EventType,
    payload: BaseModel,
    task_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
) -> EventORM:
    """Validate `payload` against the schema registered for `event_type`,
    then insert the append-only event row. The single place events are
    written, so every event on the stream is guaranteed typed (rule 5)."""
    expected = EVENT_PAYLOAD_TYPES[event_type]
    if not isinstance(payload, expected):
        raise TypeError(
            f"event {event_type} requires a {expected.__name__} payload, "
            f"got {type(payload).__name__}"
        )

    event = EventORM(
        id=uuid.uuid4(),
        run_id=run_id,
        task_id=task_id,
        agent_id=agent_id,
        type=event_type.value,
        payload=payload.model_dump(mode="json"),
    )
    session.add(event)
    session.flush()
    return event
