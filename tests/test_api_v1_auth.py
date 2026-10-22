from __future__ import annotations

import json

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.config import settings
from app.http import routers
from app.http.factory import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(
        create_app(enabled_endpoints={"media_tasks"}),
        headers={"Authorization": "Bearer test-api-token"},
    )


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
        headers={"Authorization": ""},
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


def test_legacy_api_media_tasks_requires_bearer(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
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
        headers={"Authorization": ""},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("prefix", ["/api", "/v1"])
def test_business_routes_fail_closed_without_configured_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    prefix: str,
) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "")
    response = client.get(f"{prefix}/media/tasks/runtime")
    assert response.status_code == 503


@pytest.mark.parametrize("prefix", ["/api", "/v1"])
def test_business_routes_reject_missing_and_invalid_bearer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    prefix: str,
) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "secret-token")
    assert client.get(f"{prefix}/media/tasks/runtime", headers={"Authorization": ""}).status_code == 401
    assert (
        client.get(
            f"{prefix}/media/tasks/runtime",
            headers={"Authorization": "Bearer wrong-token"},
        ).status_code
        == 401
    )


def test_api_auth_rejects_before_json_parsing(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "secret-token")
    response = client.post(
        "/api/media/tasks",
        content=b"not json",
        headers={"Authorization": "", "Content-Type": "application/json"},
    )
    assert response.status_code == 401


def test_api_request_body_limit_rejects_before_dispatch(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", "secret-token")
    monkeypatch.setattr(settings, "api_max_request_bytes", 128, raising=False)
    dispatched: list[None] = []
    monkeypatch.setattr("app.media.runtime.dispatch_sing_task", lambda *_args: dispatched.append(None))
    monkeypatch.setattr("app.media.runtime.require_celery_task_package", lambda _alias: None)
    body = {
        "request_id": "req-over-limit",
        "capability": "media.sing",
        "caller": {"source": "bot", "bot_id": 1, "plugin": "sing"},
        "payload": {"speaker": "pallas", "song_id": 1, "key": 0, "chunk_index": 0},
    }
    content = json.dumps(body, separators=(",", ":")).encode() + b" " * 256
    response = client.post(
        "/v1/media/tasks",
        content=content,
        headers={"Authorization": "Bearer secret-token", "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert not dispatched


def test_health_and_docs_remain_public_without_session_disclosure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "secret-token")
    monkeypatch.setattr(
        "app.http.endpoints.ncm_login.ncm_login_manager.get_session",
        lambda: "sensitive-ncm-session",
    )
    health = client.get("/health")
    api_health = client.get("/api/health")
    assert health.status_code == api_health.status_code == 200
    assert "sensitive-ncm-session" not in health.text + api_health.text
    assert "task_id" not in health.text + api_health.text
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 200
    schema = client.get("/openapi.json").json()
    for path in ("/api/media/tasks/runtime", "/v1/media/tasks/runtime"):
        assert schema["paths"][path]["get"]["security"]


@pytest.mark.parametrize("prefix", ["/api", "/v1"])
def test_ncm_login_session_is_not_exposed_without_bearer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    prefix: str,
) -> None:
    monkeypatch.setattr("app.http.deps.api_auth.settings.api_bearer_token", "secret-token")
    client = TestClient(create_app(enabled_endpoints={"ncm_login"}))
    monkeypatch.setattr(
        "app.http.endpoints.ncm_login.ncm_login_manager.get_session",
        lambda: "sensitive-ncm-session",
    )
    response = client.get(f"{prefix}/ncm/login/status", headers={"Authorization": ""})
    assert response.status_code == 401
    assert "sensitive-ncm-session" not in response.text


@pytest.mark.parametrize(
    "endpoint",
    [
        "chat",
        "media_assets",
        "media_models",
        "media_tasks",
        "ncm_login",
        "ncm_music",
        "ops_logs",
        "sing",
        "tts",
    ],
)
def test_each_router_category_is_protected_at_both_prefixes(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    probe_router = APIRouter()
    probe_router.add_api_route("/probe", lambda: {"endpoint": endpoint}, methods=["GET"])
    monkeypatch.setitem(routers.ENDPOINT_LOADERS, endpoint, lambda: probe_router)
    monkeypatch.setattr(settings, "api_bearer_token", "secret-token")
    client = TestClient(create_app(enabled_endpoints={endpoint}))

    for prefix in ("/api", "/v1"):
        path = f"{prefix}/probe"
        assert client.get(path).status_code == 401
        response = client.get(path, headers={"Authorization": "Bearer secret-token"})
        assert response.status_code == 200
        assert response.json() == {"endpoint": endpoint}


def test_health_declares_api_prefixes(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    api = response.json()["api"]
    assert api["recommended_prefix"] == "/v1"
    assert api["deprecated_prefix"] == "/api"
