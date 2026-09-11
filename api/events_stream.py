"""SSE event stream: the dashboard's only window into a run.

Design rule 5: the dashboard is a read model over the event stream, never
polling an agent or reaching into worker memory. This endpoint is that
read model's source — it only ever reads the append-only `events` table.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from core.db import EventORM, session_scope

router = APIRouter()

POLL_INTERVAL_SECONDS = 0.5


def stream_events(run_id: uuid.UUID, *, after_seq: int = 0) -> Iterator[str]:
    """Yield newly-appended events for `run_id` as SSE frames, forever.

    Polls Postgres rather than pushing via Redis pub/sub — acceptable for
    Phase 1's single-reader dashboard; Phase 2's queue can replace the
    polling loop without changing this function's contract.
    """
    last_seq = after_seq
    while True:
        with session_scope() as session:
            events = (
                session.execute(
                    select(EventORM)
                    .where(EventORM.run_id == run_id, EventORM.seq > last_seq)
                    .order_by(EventORM.seq)
                )
                .scalars()
                .all()
            )
            for event in events:
                last_seq = event.seq
                yield _as_sse_frame(event)
        time.sleep(POLL_INTERVAL_SECONDS)


def _as_sse_frame(event: EventORM) -> str:
    data = {
        "seq": event.seq,
        "run_id": str(event.run_id),
        "task_id": str(event.task_id) if event.task_id else None,
        "agent_id": str(event.agent_id) if event.agent_id else None,
        "type": event.type,
        "payload": event.payload,
        "ts": event.ts.isoformat(),
    }
    # Deliberately no `event:` field: the browser EventSource API only
    # routes to addEventListener(type, ...) for a named event, and the
    # dashboard wants one onmessage handler for every event type, reading
    # `type` from the JSON body instead.
    return f"id: {event.seq}\ndata: {json.dumps(data)}\n\n"


@router.get("/runs/{run_id}/events/stream")
def events_stream(run_id: uuid.UUID, after: int = Query(default=0)) -> StreamingResponse:
    return StreamingResponse(
        stream_events(run_id, after_seq=after), media_type="text/event-stream"
    )
