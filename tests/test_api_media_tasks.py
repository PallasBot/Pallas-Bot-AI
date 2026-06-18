from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.config import settings
from app.media_task_runtime import clear_media_task_runtime, get_media_task


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(enabled_endpoints={"media_tasks", "images"}))


@pytest.fixture(autouse=True)
def reset_media_task_runtime() -> None:
    clear_media_task_runtime()
    yield
    clear_media_task_runtime()


def test_submit_image_task_accepted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    with patch(
        "app.media_task_runtime.submit_image_generate",
        new=AsyncMock(
            return_value=MagicMock(
                result_state="success",
                data=MagicMock(mime_type="image/png", b64_data="aGVsbG8="),
                latency_ms=42,
                error=None,
            ),
        ),
    ):
        response = client.post(
            "/api/media/tasks",
            json={
                "request_id": "req-media-image",
                "capability": "image.generate",
                "caller": {"source": "bot", "bot_id": 1, "plugin": "draw"},
                "payload": {"prompt": "一只羊", "reference_urls": []},
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["result_state"] == "accepted"
    assert body["task_id"]
    status = client.get(f"/api/media/tasks/{body['task_id']}")
    assert status.status_code == 200
    task = status.json()
    assert task["capability"] == "image.generate"
    assert task["state"] in {"queued", "running", "succeeded"}


def test_get_media_task_not_found(client: TestClient) -> None:
    response = client.get("/api/media/tasks/missing-task")
    assert response.status_code == 404


def test_submit_image_task_disabled_returns_failed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", False)
    response = client.post(
        "/api/media/tasks",
        json={
            "request_id": "req-media-disabled",
            "capability": "image.generate",
            "caller": {"source": "bot", "bot_id": 1, "plugin": "draw"},
            "payload": {"prompt": "一只羊", "reference_urls": []},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result_state"] == "failed"
    assert body["error"]["failure_class"] == "provider_unavailable"


def test_submit_sing_task_queues_celery(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.media_task_runtime.require_celery_task_package", lambda _alias: None)
    celery_result = MagicMock(id="celery-sing-1")
    with patch("app.media_task_runtime.sing_task.delay", return_value=celery_result) as delay_mock:
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
    delay_mock.assert_called_once()
    task = get_media_task(body["task_id"])
    assert task is not None
    assert task.state == "queued"


def test_media_task_runtime_status(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    with patch(
        "app.media_task_runtime.submit_image_generate",
        new=AsyncMock(
            return_value=MagicMock(
                result_state="success",
                data=MagicMock(mime_type="image/png", b64_data="aGVsbG8="),
                latency_ms=10,
                error=None,
            ),
        ),
    ):
        client.post(
            "/api/media/tasks",
            json={
                "request_id": "req-media-runtime",
                "capability": "image.generate",
                "caller": {"source": "bot", "bot_id": 1, "plugin": "draw"},
                "payload": {"prompt": "测试", "reference_urls": []},
            },
        )
    runtime = client.get("/api/media/tasks/runtime")
    assert runtime.status_code == 200
    body = runtime.json()
    assert body["total_tasks"] >= 1
    assert any(item["capability"] == "image.generate" for item in body["capabilities"])


def test_health_includes_media_tasks(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "media_tasks" in body
    assert body["media_tasks"]["health_state"] in {"healthy", "degraded", "unhealthy", "unknown"}


def test_health_includes_tts() -> None:
    client = TestClient(create_app(enabled_endpoints={"media_tasks", "images", "tts"}))
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert "tts" in body
    assert body["tts"]["capability"] == "tts.synthesize"


def test_image_generate_force_task_mode_returns_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    with patch(
        "app.media_task_runtime.submit_image_generate",
        new=AsyncMock(
            return_value=MagicMock(
                result_state="success",
                data=MagicMock(mime_type="image/png", b64_data="aGVsbG8="),
                latency_ms=10,
                error=None,
            ),
        ),
    ):
        response = client.post(
            "/api/images/generate",
            json={
                "request_id": "req-image-task-mode",
                "capability": "image.generate",
                "caller": {"source": "bot", "bot_id": 1, "plugin": "draw"},
                "policy": {"force_task_mode": True},
                "payload": {"prompt": "一只羊", "reference_urls": []},
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["result_state"] == "accepted"
    assert body["task_id"]
