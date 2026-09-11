import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from workers.hardcoded_worker import ensure_agent


def test_create_run_creates_a_run_and_its_one_task(client: TestClient) -> None:
    response = client.post(
        "/runs",
        json={"goal": "ship phase 1", "instructions": "write a one-line README"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["goal"] == "ship phase 1"
    assert body["run"]["status"] == "running"
    assert body["task"]["run_id"] == body["run"]["id"]
    assert body["task"]["status"] == "pending"
    assert body["task"]["spec"]["instructions"] == "write a one-line README"


def test_create_run_rejects_unknown_fields(client: TestClient) -> None:
    response = client.post(
        "/runs",
        json={"goal": "x", "instructions": "y", "not_a_real_field": True},
    )

    assert response.status_code == 422


def test_kill_task_flips_a_pending_task_to_cancelled(client: TestClient) -> None:
    created = client.post(
        "/runs", json={"goal": "ship phase 1", "instructions": "do it"}
    ).json()
    task_id = created["task"]["id"]

    response = client.post(f"/tasks/{task_id}/kill")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_kill_task_is_rejected_once_terminal(client: TestClient) -> None:
    created = client.post(
        "/runs", json={"goal": "ship phase 1", "instructions": "do it"}
    ).json()
    task_id = created["task"]["id"]

    first = client.post(f"/tasks/{task_id}/kill")
    assert first.status_code == 200

    second = client.post(f"/tasks/{task_id}/kill")
    assert second.status_code == 409


def test_kill_task_404s_for_an_unknown_task(client: TestClient) -> None:
    response = client.post(f"/tasks/{uuid.uuid4()}/kill")

    assert response.status_code == 404


def test_get_run_404s_for_an_unknown_run(client: TestClient) -> None:
    response = client.get(f"/runs/{uuid.uuid4()}")

    assert response.status_code == 404


def test_list_run_tasks_returns_its_task(client: TestClient) -> None:
    created = client.post(
        "/runs", json={"goal": "ship phase 1", "instructions": "do it"}
    ).json()
    run_id = created["run"]["id"]

    response = client.get(f"/runs/{run_id}/tasks")

    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == created["task"]["id"]


def test_list_agents_returns_the_hardcoded_worker(client: TestClient, pg_session: Session) -> None:
    ensure_agent(pg_session, name="hardcoded-worker", role="planner", tier="planner")
    pg_session.commit()

    response = client.get("/agents")

    assert response.status_code == 200
    names = [a["name"] for a in response.json()]
    assert "hardcoded-worker" in names
