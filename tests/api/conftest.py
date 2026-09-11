from collections.abc import Generator, Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.deps import get_db
from api.main import app
from core.db import session_scope


@pytest.fixture
def client(_migrated_pg_url: str, pg_engine: sa.Engine) -> Iterator[TestClient]:
    """pg_engine is depended on only so its fixture cleanup (truncating
    every table) also runs after tests that drive the API through HTTP,
    where each request commits its own session independently."""

    def override_get_db() -> Generator[Session, None, None]:
        with session_scope(_migrated_pg_url) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
