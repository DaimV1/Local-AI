"""Structural checks on the ORM metadata that don't need a live Postgres.

The read/write integration tests against a real database live in
tests/core/test_db_integration.py and skip when DATABASE_URL isn't
reachable (e.g. in this sandbox, which has no Docker daemon).
"""

from core.db import Base

EXPECTED_TABLES = {"agents", "runs", "tasks", "events", "artifacts", "approvals"}


def test_all_six_data_model_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_events_table_is_indexed_by_run_id_and_ts() -> None:
    events = Base.metadata.tables["events"]
    index_columns = {tuple(ix.columns.keys()) for ix in events.indexes}

    assert ("run_id", "ts") in index_columns


def test_tasks_table_is_indexed_by_status_and_claimed_by() -> None:
    tasks = Base.metadata.tables["tasks"]
    index_columns = {tuple(ix.columns.keys()) for ix in tasks.indexes}

    assert ("status", "claimed_by") in index_columns


def test_artifacts_requires_a_path_or_a_content_ref() -> None:
    artifacts = Base.metadata.tables["artifacts"]
    check_names = {c.name for c in artifacts.constraints if hasattr(c, "name")}

    assert "ck_artifacts_ref" in check_names
