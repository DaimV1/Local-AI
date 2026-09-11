"""Shared fixtures for integration tests that need a live Postgres.

This sandbox has no Docker daemon, so these tests skip here and only run
where docker compose has actually brought up `postgres` (i.e. on your
workstation, per the RUNBOOK).
"""

import os
import subprocess
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://local_ai:change-me@localhost:5432/local_ai_test",
)


def _postgres_reachable(url: str) -> bool:
    try:
        engine = sa.create_engine(url)
        with engine.connect():
            return True
    except Exception:
        return False
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def pg_url() -> str:
    if not _postgres_reachable(TEST_DATABASE_URL):
        pytest.skip(f"Postgres not reachable at {TEST_DATABASE_URL} (needs docker compose up)")
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def _migrated_pg_url(pg_url: str) -> str:
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": pg_url},
        check=True,
    )
    return pg_url


@pytest.fixture
def pg_session(_migrated_pg_url: str) -> Generator[Session, None, None]:
    import core.db as db_module
    from core.db import get_engine, get_sessionmaker

    db_module._engine = None
    db_module._SessionLocal = None

    engine = get_engine(_migrated_pg_url)
    session = get_sessionmaker(_migrated_pg_url)()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        tables = ["events", "artifacts", "approvals", "tasks", "runs", "agents"]
        with engine.begin() as conn:
            conn.execute(sa.text(f"TRUNCATE TABLE {', '.join(tables)} CASCADE"))
