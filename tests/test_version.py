from __future__ import annotations

from pathlib import Path
from tomllib import loads

from app.core import celery
from app.http.factory import API_VERSION, create_app
from app.version import VERSION


def test_version_is_exposed_by_http_api() -> None:
    app = create_app(enabled_endpoints=set())

    assert VERSION == "4.1.0"
    assert API_VERSION == VERSION
    assert app.version == VERSION


def test_health_reports_package_version() -> None:
    app = create_app(enabled_endpoints=set())
    health_route = next(route for route in app.routes if route.path == "/health")

    assert health_route.endpoint()["api_version"] == VERSION


def test_celery_startup_summary_uses_package_version(monkeypatch) -> None:
    captured: list[dict[str, str]] = []
    monkeypatch.setattr(celery, "sweep_gpu_lock_state_on_worker_startup", lambda: None)
    monkeypatch.setattr(celery, "ping_redis_sync", lambda: True)
    monkeypatch.setattr(celery, "register_startup_fact", lambda *args: None)
    monkeypatch.setattr(celery, "emit_startup_summary", lambda **kwargs: captured.append(kwargs))

    celery.on_celery_worker_ready()

    assert captured == [{"api_version": VERSION, "role": "celery"}]


def test_project_installs_pallas_ai_console_script() -> None:
    pyproject = loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["pallas-ai"] == "app.cli:main"
    assert pyproject["tool"]["uv"]["package"] is True
    assert pyproject["build-system"]["build-backend"] == "setuptools.build_meta"
