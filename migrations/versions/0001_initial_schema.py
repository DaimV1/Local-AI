"""Initial schema: agents, runs, tasks, events, artifacts, approvals.

Revision ID: 0001
Revises:
Create Date: 2026-09-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column(
            "tool_allowlist", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="idle"),
        sa.Column("last_heartbeat", sa.TIMESTAMP(timezone=True)),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('idle','working','paused','dead')", name="ck_agents_status"
        ),
    )

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.Text(), nullable=False, server_default="local-user"),
        sa.Column("budget", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column("git_branch", sa.Text()),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_runs_status",
        ),
    )

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False
        ),
        sa.Column("parent_task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id")),
        sa.Column("group_id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("spec", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("claimed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id")),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "budget_remaining", postgresql.JSONB(), nullable=False, server_default="{}"
        ),
        sa.Column("result", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('pending','claimed','running','blocked',"
            "'awaiting_approval','done','failed','cancelled')",
            name="ck_tasks_status",
        ),
    )
    op.create_index("ix_tasks_status_claimed_by", "tasks", ["status", "claimed_by"])
    op.create_index("ix_tasks_run_id", "tasks", ["run_id"])

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False, unique=True),
        sa.Column(
            "run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id")),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id")),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "ts", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_events_run_id_ts", "events", ["run_id", "ts"])

    # Design rule: events are append-only. Reject UPDATE/DELETE at the
    # database level so a bug can't silently rewrite history.
    op.execute(
        """
        CREATE FUNCTION reject_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'events is append-only: % on events is not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER events_immutable
        BEFORE UPDATE OR DELETE ON events
        FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();
        """
    )

    op.create_table(
        "artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id")),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("path", sa.Text()),
        sa.Column("content_ref", sa.Text()),
        sa.Column("git_sha", sa.Text()),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "kind IN ('file','diff','report','verdict')", name="ck_artifacts_kind"
        ),
        sa.CheckConstraint(
            "path IS NOT NULL OR content_ref IS NOT NULL", name="ck_artifacts_ref"
        ),
    )

    op.create_table(
        "approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id"), nullable=False
        ),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id")),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "requested_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("decision", sa.Text()),
        sa.Column("decided_by", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint("decision IN ('approved','rejected')", name="ck_approvals_decision"),
    )


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_table("artifacts")
    op.execute("DROP TRIGGER IF EXISTS events_immutable ON events;")
    op.execute("DROP FUNCTION IF EXISTS reject_event_mutation();")
    op.drop_index("ix_events_run_id_ts", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_tasks_run_id", table_name="tasks")
    op.drop_index("ix_tasks_status_claimed_by", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("runs")
    op.drop_table("agents")
