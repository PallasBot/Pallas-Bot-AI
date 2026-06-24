from __future__ import annotations

from fastapi.testclient import TestClient

from app.app_factory import create_app


def test_embeddings_endpoint_returns_vectors() -> None:
    client = TestClient(create_app(enabled_endpoints={"embeddings"}))
    response = client.post("/api/v1/embeddings", json={"input": "hello", "model": "stub"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    assert len(payload["data"]) == 1
    assert len(payload["data"][0]["embedding"]) == 16
