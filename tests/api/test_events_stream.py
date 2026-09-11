"""stream_events is tested as a plain generator, not through real HTTP:
it polls forever with a sleep, which doesn't play well with a test
client's request/response lifecycle. Pulling a bounded number of items
off the generator directly still exercises the real DB read path.
"""

import uuid

from sqlalchemy.orm import Session

from api.events_stream import stream_events
from core.db import RunORM, record_event
from core.events import EventType, RunStartedPayload, TaskCreatedPayload


def test_stream_events_yields_existing_events_as_sse_frames(pg_session: Session) -> None:
    run = RunORM(id=uuid.uuid4(), goal="ship phase 1", workspace_path="/workspaces/run-1")
    pg_session.add(run)
    pg_session.flush()

    record_event(
        pg_session,
        run_id=run.id,
        event_type=EventType.RUN_STARTED,
        payload=RunStartedPayload(goal="ship phase 1"),
    )
    record_event(
        pg_session,
        run_id=run.id,
        event_type=EventType.TASK_CREATED,
        payload=TaskCreatedPayload(title="write the readme"),
    )
    pg_session.commit()

    gen = stream_events(run.id, after_seq=0)
    first = next(gen)
    second = next(gen)

    assert '"type": "run_started"' in first
    assert '"goal": "ship phase 1"' in first
    assert '"type": "task_created"' in second


def test_stream_events_after_seq_skips_earlier_events(pg_session: Session) -> None:
    run = RunORM(id=uuid.uuid4(), goal="ship phase 1", workspace_path="/workspaces/run-1")
    pg_session.add(run)
    pg_session.flush()

    first_event = record_event(
        pg_session,
        run_id=run.id,
        event_type=EventType.RUN_STARTED,
        payload=RunStartedPayload(goal="ship phase 1"),
    )
    record_event(
        pg_session,
        run_id=run.id,
        event_type=EventType.TASK_CREATED,
        payload=TaskCreatedPayload(title="write the readme"),
    )
    pg_session.commit()

    gen = stream_events(run.id, after_seq=first_event.seq)
    only_frame = next(gen)

    assert '"type": "task_created"' in only_frame
