from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.http.factory import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(enabled_endpoints={"media_tasks"}))


def test_v1_media_tasks_requires_bearer_when_token_set(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "secret-token")
    response = client.post(
        "/v1/media/tasks",
        json={
            "request_id": "req-v1-auth",
            "capability": "media.sing",
            "caller": {"source": "bot", "bot_id": 1, "plugin": "sing"},
            "payload": {"speaker": "pallas", "song_id": 1, "key": 0, "chunk_index": 0},
        },
    )
    assert response.status_code == 401


def test_v1_media_tasks_accepts_bearer(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "secret-token")
    monkeypatch.setattr("app.media.runtime.dispatch_sing_task", lambda record, body: None)
    monkeypatch.setattr("app.media.runtime.require_celery_task_package", lambda _alias: None)
    response = client.post(
        "/v1/media/tasks",
        json={
            "request_id": "req-v1-ok",
            "capability": "media.sing",
            "caller": {"source": "bot", "bot_id": 1, "plugin": "sing"},
            "payload": {"speaker": "pallas", "song_id": 1, "key": 0, "chunk_index": 0},
        },
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 200
    assert response.json()["result_state"] == "accepted"


def test_legacy_api_media_tasks_no_bearer_without_ops(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "secret-token")
    monkeypatch.setattr("app.media.runtime.dispatch_sing_task", lambda record, body: None)
    monkeypatch.setattr("app.media.runtime.require_celery_task_package", lambda _alias: None)
    response = client.post(
        "/api/media/tasks",
        json={
            "request_id": "req-legacy-no-auth",
            "capability": "media.sing",
            "caller": {"source": "bot", "bot_id": 1, "plugin": "sing"},
            "payload": {"speaker": "pallas", "song_id": 1, "key": 0, "chunk_index": 0},
        },
    )
    assert response.status_code == 200


def test_health_declares_api_prefixes(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    api = response.json()["api"]
    assert api["recommended_prefix"] == "/v1"
    assert api["deprecated_prefix"] == "/api"
