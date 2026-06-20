from __future__ import annotations

from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.config import settings


def test_get_local_routing_config_returns_current_payload(monkeypatch) -> None:
    app = create_app(enabled_endpoints={"llm_providers"})
    client = TestClient(app)
    monkeypatch.setattr(settings, "llm_chat_enabled", True)
    monkeypatch.setattr(
        "app.api.endpoints.llm_providers.export_local_routing_config",
        lambda: {
            "llm_model": "qwen3:8b",
            "local_multi_model_enabled": True,
            "moe_models": {
                "simple": "qwen2.5:0.5b",
                "medium": "qwen2.5:7b",
                "complex": "qwen3.5:9b",
                "vision": "",
            },
            "task_models": {
                "llm_chat": "",
                "drunk": "",
                "repeater_fallback": "",
                "repeater_polish": "",
                "repeater_polish_lite": "qwen2.5:0.5b",
                "repeater_select": "qwen2.5:0.5b",
            },
            "env_file": "/tmp/test.env",
        },
    )

    response = client.get("/api/llm/local-routing")

    assert response.status_code == 200
    body = response.json()
    assert body["llm_model"] == "qwen3:8b"
    assert body["local_multi_model_enabled"] is True
    assert body["task_models"]["repeater_select"] == "qwen2.5:0.5b"


def test_put_local_routing_config_saves_payload(monkeypatch) -> None:
    app = create_app(enabled_endpoints={"llm_providers"})
    client = TestClient(app)
    monkeypatch.setattr(settings, "llm_chat_enabled", True)
    captured: dict[str, object] = {}

    def fake_save(document: dict[str, object]) -> dict[str, object]:
        captured.update(document)
        return {
            **document,
            "env_file": "/tmp/test.env",
        }

    monkeypatch.setattr("app.api.endpoints.llm_providers.save_local_routing_config", fake_save)

    response = client.put(
        "/api/llm/local-routing",
        json={
            "llm_model": "qwen3:8b",
            "local_multi_model_enabled": True,
            "moe_models": {
                "simple": "qwen2.5:0.5b",
                "medium": "qwen2.5:7b",
                "complex": "qwen3.5:9b",
                "vision": "",
            },
            "task_models": {
                "llm_chat": "",
                "drunk": "",
                "repeater_fallback": "",
                "repeater_polish": "",
                "repeater_polish_lite": "qwen2.5:0.5b",
                "repeater_select": "qwen2.5:0.5b",
            },
            "env_file": "",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert captured["llm_model"] == "qwen3:8b"
    assert captured["local_multi_model_enabled"] is True
    assert body["env_file"] == "/tmp/test.env"


def test_local_routing_config_disabled_returns_503(monkeypatch) -> None:
    app = create_app(enabled_endpoints={"llm_providers"})
    client = TestClient(app)
    monkeypatch.setattr(settings, "llm_chat_enabled", False)

    response = client.get("/api/llm/local-routing")

    assert response.status_code == 503
