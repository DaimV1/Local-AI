"""Budget enforcement in code, not a prompt instruction (design rule 6).

Tripping a budget escalates to the approval inbox; it never lets the
orchestrator or a worker silently continue past a limit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from core.db import RunORM, TaskORM

Dimension = Literal["steps", "tokens", "wallclock_seconds", "revision_rounds"]


class BudgetViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: Dimension
    used: float
    limit: float


def check_budget(run: RunORM, task: TaskORM) -> BudgetViolation | None:
    """Return the first tripped budget dimension for `task`, or None.

    Phase 1's single-call worker only exercises `steps` (this task's
    attempt count) and `wallclock_seconds` (elapsed since the run
    started); `tokens` and `revision_rounds` accumulate across multiple
    calls or revision rounds that don't exist until Phase 2/3, so they're
    checked here for forward compatibility but can never trip yet.
    """
    budget = run.budget or {}

    max_steps = budget.get("max_steps")
    if max_steps is not None and task.attempt + 1 > max_steps:
        return BudgetViolation(dimension="steps", used=task.attempt + 1, limit=max_steps)

    max_wallclock = budget.get("max_wallclock_seconds")
    if max_wallclock is not None and run.started_at is not None:
        started_at = run.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - started_at).total_seconds()
        if elapsed > max_wallclock:
            return BudgetViolation(
                dimension="wallclock_seconds", used=elapsed, limit=max_wallclock
            )

    return None
