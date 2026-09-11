from uuid import uuid4

import pytest

from core.db import record_event
from core.events import EventType, RunStartedPayload, TaskClaimedPayload


class _NoOpSession:
    """Enough of the Session interface for record_event's type-check path,
    without touching a real database."""

    def add(self, _obj: object) -> None:
        pass

    def flush(self) -> None:
        pass


def test_record_event_rejects_a_payload_that_does_not_match_the_event_type() -> None:
    with pytest.raises(TypeError, match="requires a RunStartedPayload payload"):
        record_event(
            _NoOpSession(),  # type: ignore[arg-type]
            run_id=uuid4(),
            event_type=EventType.RUN_STARTED,
            payload=TaskClaimedPayload(),
        )


def test_record_event_accepts_a_matching_payload_and_serializes_it() -> None:
    session = _NoOpSession()

    event = record_event(
        session,  # type: ignore[arg-type]
        run_id=uuid4(),
        event_type=EventType.RUN_STARTED,
        payload=RunStartedPayload(goal="ship phase 1"),
    )

    assert event.type == "run_started"
    assert event.payload == {"goal": "ship phase 1"}
