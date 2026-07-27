from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.http.factory import create_app
from app.media.runtime import clear_media_task_runtime
from app.media.store import MediaTaskRecord, get_record, store_task_record, update_task_record


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(enabled_endpoints={"media_tasks"}))


@pytest.fixture(autouse=True)
def reset_media_task_runtime() -> None:
    clear_media_task_runtime()
    yield
    clear_media_task_runtime()


def test_get_media_task_not_found(client: TestClient) -> None:
    response = client.get("/api/media/tasks/missing-task")
    assert response.status_code == 404


def test_submit_sing_task_queues_celery(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.media.runtime.require_celery_task_package", lambda _alias: None)
    calls: list[tuple[str, str]] = []

    def fake_dispatch(record, body) -> None:
        calls.append((record.task_id, body.request_id))
        update_task_record(record.task_id, celery_task_id="celery-sing-1", state="queued")

    monkeypatch.setattr("app.media.runtime.dispatch_sing_task", fake_dispatch)
    response = client.post(
        "/api/media/tasks",
        json={
            "request_id": "req-media-sing",
            "capability": "media.sing",
            "caller": {"source": "bot", "bot_id": 1, "plugin": "sing"},
            "payload": {
                "speaker": "帕拉斯",
                "song_id": 12345,
                "key": 0,
                "chunk_index": 0,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result_state"] == "accepted"
    assert calls == [(body["task_id"], "req-media-sing")]
    task = get_record(body["task_id"])
    assert task is not None
    assert task.state == "queued"


def test_media_task_runtime_status_exposes_state_counts(client: TestClient) -> None:
    store_task_record(
        MediaTaskRecord(
            task_id="task-runtime-q",
            request_id="req-runtime-q",
            capability="media.sing",
            state="queued",
            provider_id="sing",
            backend_id="sing-local",
            submitted_at=1.0,
        )
    )
    store_task_record(
        MediaTaskRecord(
            task_id="task-runtime-f",
            request_id="req-runtime-f",
            capability="media.sing",
            state="failed",
            provider_id="sing",
            backend_id="sing-local",
            submitted_at=2.0,
        )
    )

    runtime = client.get("/api/media/tasks/runtime")

    assert runtime.status_code == 200
    body = runtime.json()
    assert body["state_counts"]["queued"] == 1
    assert body["state_counts"]["failed"] == 1


def test_health_includes_media_tasks(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "media_tasks" in body
    assert body["media_tasks"]["health_state"] in {"healthy", "degraded", "unhealthy", "unknown"}


def test_health_includes_tts() -> None:
    client = TestClient(create_app(enabled_endpoints={"media_tasks", "tts"}))
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "tts" in body
    assert body["tts"]["capability"] == "tts.synthesize"
