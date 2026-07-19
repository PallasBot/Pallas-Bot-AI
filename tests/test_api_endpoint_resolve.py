from __future__ import annotations

from app.api.routers import LLM_CORE_ENDPOINTS, resolve_enabled_endpoints


def test_resolve_enabled_endpoints_llm_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routers.celery_task_package_enabled",
        lambda alias: alias == "llm",
    )
    selected = resolve_enabled_endpoints()
    assert selected == LLM_CORE_ENDPOINTS
    assert "sing" not in selected
    assert "tts" not in selected
    assert "chat" not in selected
    assert "ncm_login" not in selected


def test_resolve_enabled_endpoints_with_media(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.routers.celery_task_package_enabled",
        lambda alias: alias in {"llm", "sing", "tts"},
    )
    selected = resolve_enabled_endpoints()
    assert "sing" in selected
    assert "tts" in selected
    assert "ncm_login" in selected
    assert "llm_chat" in selected


def test_resolve_enabled_endpoints_explicit_override() -> None:
    assert resolve_enabled_endpoints({"llm_chat"}) == frozenset({"llm_chat"})
    assert resolve_enabled_endpoints(set()) == frozenset()
