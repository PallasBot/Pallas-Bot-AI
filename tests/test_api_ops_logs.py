from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.services.service_logs import resolve_service_log_path, tail_log_lines


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(enabled_endpoints={"ops_logs"}))


def test_resolve_service_log_path_prefers_uvicorn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("app\n", encoding="utf-8")
    (logs / "uvicorn.log").write_text("uvicorn\n", encoding="utf-8")
    monkeypatch.setattr("app.services.service_logs.settings.log_path", str(logs))
    picked = resolve_service_log_path("uvicorn")
    assert picked is not None
    assert picked.name == "uvicorn.log"


def test_tail_log_lines_reads_recent(tmp_path: Path) -> None:
    path = tmp_path / "big.log"
    path.write_text("line-1\nline-2\nline-3\n", encoding="utf-8")
    assert tail_log_lines(path, 2) == ["line-2", "line-3"]


def test_ops_logs_endpoint_returns_tail(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "celery.log").write_text("a\nb\nc\n", encoding="utf-8")
    monkeypatch.setattr("app.services.service_logs.settings.log_path", str(logs))

    resp = client.get("/api/ops/logs", params={"kind": "celery", "n": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lines"] == ["b", "c"]
    assert body["error"] is None
    assert body["source"] == "ai"


def test_ops_logs_endpoint_missing_file(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr("app.services.service_logs.settings.log_path", str(logs))

    resp = client.get("/api/ops/logs", params={"kind": "uvicorn"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["lines"] == []
    assert body["error"] == "日志文件不存在"


def test_ops_logs_requires_bearer_when_token_configured(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "uvicorn.log").write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr("app.services.service_logs.settings.log_path", str(logs))
    monkeypatch.setattr("app.api.deps.api_auth.settings.api_bearer_token", "secret-token")

    denied = client.get("/api/ops/logs", params={"kind": "uvicorn"})
    assert denied.status_code == 401

    ok = client.get(
        "/api/ops/logs",
        params={"kind": "uvicorn"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert ok.status_code == 200
    assert ok.json()["lines"] == ["ok"]
