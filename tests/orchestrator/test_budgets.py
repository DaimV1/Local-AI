from datetime import UTC, datetime, timedelta

from core.db import RunORM, TaskORM
from orchestrator.budgets import check_budget


def _run(**overrides: object) -> RunORM:
    defaults: dict[str, object] = {
        "goal": "ship phase 1",
        "workspace_path": "/workspaces/run-1",
        "budget": {},
        "started_at": None,
    }
    return RunORM(**{**defaults, **overrides})


def _task(**overrides: object) -> TaskORM:
    defaults: dict[str, object] = {
        "title": "write the readme",
        "spec": {"role": "planner", "instructions": "write README.md"},
        "attempt": 0,
    }
    return TaskORM(**{**defaults, **overrides})


def test_no_budget_configured_never_trips() -> None:
    assert check_budget(_run(budget={}), _task()) is None


def test_steps_within_limit_passes() -> None:
    run = _run(budget={"max_steps": 3})
    task = _task(attempt=1)  # this would be the 2nd attempt

    assert check_budget(run, task) is None


def test_steps_over_limit_trips() -> None:
    run = _run(budget={"max_steps": 1})
    task = _task(attempt=1)  # this would be the 2nd attempt

    violation = check_budget(run, task)

    assert violation is not None
    assert violation.dimension == "steps"
    assert violation.used == 2
    assert violation.limit == 1


def test_wallclock_without_started_at_never_trips() -> None:
    run = _run(budget={"max_wallclock_seconds": 1}, started_at=None)

    assert check_budget(run, _task()) is None


def test_wallclock_within_limit_passes() -> None:
    run = _run(
        budget={"max_wallclock_seconds": 3600},
        started_at=datetime.now(UTC) - timedelta(seconds=5),
    )

    assert check_budget(run, _task()) is None


def test_wallclock_over_limit_trips() -> None:
    run = _run(
        budget={"max_wallclock_seconds": 1},
        started_at=datetime.now(UTC) - timedelta(seconds=60),
    )

    violation = check_budget(run, _task())

    assert violation is not None
    assert violation.dimension == "wallclock_seconds"
    assert violation.limit == 1


def test_naive_started_at_is_treated_as_utc() -> None:
    naive_now = datetime.now(UTC).replace(tzinfo=None)
    run = _run(budget={"max_wallclock_seconds": 3600}, started_at=naive_now)

    assert check_budget(run, _task()) is None


def test_steps_checked_before_wallclock() -> None:
    run = _run(
        budget={"max_steps": 1, "max_wallclock_seconds": 3600},
        started_at=datetime.now(UTC),
    )
    task = _task(attempt=1)

    violation = check_budget(run, task)

    assert violation is not None
    assert violation.dimension == "steps"
