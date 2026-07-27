from __future__ import annotations

from app.http.routers import MEDIA_CORE_ENDPOINTS, resolve_enabled_endpoints


def test_resolve_enabled_endpoints_media_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.http.routers.celery_task_package_enabled",
        lambda alias: False,
    )
    selected = resolve_enabled_endpoints()
    assert selected == MEDIA_CORE_ENDPOINTS
    assert "sing" not in selected
    assert "tts" not in selected
    assert "chat" not in selected
    assert "ncm_login" not in selected


def test_resolve_enabled_endpoints_with_media(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.http.routers.celery_task_package_enabled",
        lambda alias: alias in {"sing", "tts"},
    )
    selected = resolve_enabled_endpoints()
    assert "sing" in selected
    assert "tts" in selected
    assert "ncm_login" in selected
    assert "media_tasks" in selected


def test_resolve_enabled_endpoints_explicit_override() -> None:
    assert resolve_enabled_endpoints({"media_tasks"}) == frozenset({"media_tasks"})
    assert resolve_enabled_endpoints(set()) == frozenset()
