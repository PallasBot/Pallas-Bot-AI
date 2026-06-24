from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.config import settings
from app.image_runtime import clear_image_runtime_state


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(enabled_endpoints={"images"}))


@pytest.fixture(autouse=True)
def reset_image_runtime_state() -> None:
    clear_image_runtime_state()
    yield
    clear_image_runtime_state()


def test_image_generate_disabled_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", False)
    response = client.post(
        "/api/images/generate",
        json={
            "request_id": "req-image-disabled",
            "capability": "image.generate",
            "caller": {"source": "bot", "bot_id": 1, "plugin": "pallas_plugin_draw"},
            "payload": {"prompt": "一只羊", "reference_urls": []},
        },
    )
    assert response.status_code == 503


def test_images_only_app_does_not_mount_chat_route(client: TestClient) -> None:
    response = client.post("/api/chat/req-anything", json={})
    assert response.status_code == 404


def test_image_generate_enabled_returns_runtime_result(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    with patch(
        "app.api.endpoints.images.submit_image_generate",
        new=AsyncMock(
            return_value={
                "request_id": "req-image-ok",
                "result_state": "success",
                "capability": "image.generate",
                "provider_id": "image-gateway",
                "backend_id": "image-primary",
                "data": {"mime_type": "image/png", "b64_data": "aGVsbG8="},
                "error": None,
            }
        ),
    ):
        response = client.post(
            "/api/images/generate",
            json={
                "request_id": "req-image-ok",
                "capability": "image.generate",
                "caller": {"source": "bot", "bot_id": 1, "plugin": "pallas_plugin_draw"},
                "payload": {"prompt": "一只羊", "reference_urls": []},
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["result_state"] == "success"
    assert body["provider_id"] == "image-gateway"
    assert body["backend_id"] == "image-primary"


def test_runtime_status_updates_after_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    monkeypatch.setattr(settings, "image_base_url", "https://image.example.com")
    monkeypatch.setattr(settings, "image_api_key", "secret")
    monkeypatch.setattr(settings, "image_model", "gpt-image-1")
    with patch(
        "app.api.endpoints.images.submit_image_generate",
        new=AsyncMock(
            return_value={
                "request_id": "req-image-ok",
                "result_state": "success",
                "capability": "image.generate",
                "provider_id": "image-gateway",
                "backend_id": "image-primary",
                "latency_ms": 120,
                "data": {"mime_type": "image/png", "b64_data": "aGVsbG8="},
                "error": None,
            }
        ),
    ):
        client.post(
            "/api/images/generate",
            json={
                "request_id": "req-image-ok",
                "capability": "image.generate",
                "caller": {"source": "bot", "bot_id": 1, "plugin": "pallas_plugin_draw"},
                "payload": {"prompt": "一只羊", "reference_urls": []},
            },
        )
    runtime = client.get("/api/images/runtime")
    assert runtime.status_code == 200
    body = runtime.json()
    backend = body["backends"][0]
    assert backend["health_state"] == "healthy"
    assert backend["last_latency_ms"] == 120
    assert backend["consecutive_failures"] == 0


def test_runtime_status_updates_after_failure(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    with patch(
        "app.api.endpoints.images.submit_image_generate",
        new=AsyncMock(
            return_value={
                "request_id": "req-image-fail",
                "result_state": "failed",
                "capability": "image.generate",
                "provider_id": "image-gateway",
                "backend_id": "image-primary",
                "error": {
                    "code": "image_timeout",
                    "message": "timeout",
                    "retryable": True,
                    "failure_class": "timeout",
                },
            }
        ),
    ):
        client.post(
            "/api/images/generate",
            json={
                "request_id": "req-image-fail",
                "capability": "image.generate",
                "caller": {"source": "bot", "bot_id": 1, "plugin": "pallas_plugin_draw"},
                "payload": {"prompt": "一只羊", "reference_urls": []},
            },
        )
    runtime = client.get("/api/images/runtime")
    assert runtime.status_code == 200
    body = runtime.json()
    backend = body["backends"][0]
    assert backend["consecutive_failures"] == 1
    assert backend["recent_failure_class"] == "timeout"


def test_runtime_opens_circuit_after_repeated_failures(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    with patch(
        "app.api.endpoints.images.submit_image_generate",
        new=AsyncMock(
            return_value={
                "request_id": "req-image-fail",
                "result_state": "failed",
                "capability": "image.generate",
                "provider_id": "image-gateway",
                "backend_id": "image-primary",
                "error": {
                    "code": "image_timeout",
                    "message": "timeout",
                    "retryable": True,
                    "failure_class": "timeout",
                },
            }
        ),
    ):
        for idx in range(3):
            client.post(
                "/api/images/generate",
                json={
                    "request_id": f"req-image-fail-{idx}",
                    "capability": "image.generate",
                    "caller": {"source": "bot", "bot_id": 1, "plugin": "pallas_plugin_draw"},
                    "payload": {"prompt": "一只羊", "reference_urls": []},
                },
            )
    runtime = client.get("/api/images/runtime")
    body = runtime.json()
    backend = body["backends"][0]
    assert backend["circuit_state"] == "open"
    assert body["degraded_state"] == "degraded"
    assert body["health_state"] == "degraded"


def test_runtime_success_closes_circuit_and_clears_failures(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    monkeypatch.setattr(settings, "image_base_url", "https://image.example.com")
    monkeypatch.setattr(settings, "image_api_key", "secret")
    monkeypatch.setattr(settings, "image_model", "gpt-image-1")
    with patch(
        "app.api.endpoints.images.submit_image_generate",
        new=AsyncMock(
            side_effect=[
                {
                    "request_id": "req-image-fail",
                    "result_state": "failed",
                    "capability": "image.generate",
                    "provider_id": "image-gateway",
                    "backend_id": "image-primary",
                    "error": {
                        "code": "image_timeout",
                        "message": "timeout",
                        "retryable": True,
                        "failure_class": "timeout",
                    },
                },
                {
                    "request_id": "req-image-ok",
                    "result_state": "success",
                    "capability": "image.generate",
                    "provider_id": "image-gateway",
                    "backend_id": "image-primary",
                    "latency_ms": 88,
                    "data": {"mime_type": "image/png", "b64_data": "aGVsbG8="},
                    "error": None,
                },
            ]
        ),
    ):
        client.post(
            "/api/images/generate",
            json={
                "request_id": "req-image-fail",
                "capability": "image.generate",
                "caller": {"source": "bot", "bot_id": 1, "plugin": "pallas_plugin_draw"},
                "payload": {"prompt": "一只羊", "reference_urls": []},
            },
        )
        client.post(
            "/api/images/generate",
            json={
                "request_id": "req-image-ok",
                "capability": "image.generate",
                "caller": {"source": "bot", "bot_id": 1, "plugin": "pallas_plugin_draw"},
                "payload": {"prompt": "一只羊", "reference_urls": []},
            },
        )
    runtime = client.get("/api/images/runtime")
    body = runtime.json()
    backend = body["backends"][0]
    assert backend["circuit_state"] == "closed"
    assert backend["consecutive_failures"] == 0
    assert body["degraded_state"] == "normal"
    assert body["health_state"] == "healthy"
