from __future__ import annotations

from fastapi.testclient import TestClient

from app.app_factory import create_app


def test_health_and_api_health_alias_match() -> None:
    client = TestClient(create_app(enabled_endpoints={"llm_chat"}))
    root = client.get("/health")
    aliased = client.get("/api/health")
    assert root.status_code == 200
    assert aliased.status_code == 200
    assert root.json()["status"] == "ok"
    assert aliased.json() == root.json()
