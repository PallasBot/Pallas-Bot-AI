from __future__ import annotations

import pytest

from app.core.config import Settings
from app.providers.router import provider_configuration_error, provider_reachability


def test_provider_configuration_error_remote_only_missing_remote() -> None:
    cfg = Settings(
        llm_chat_enabled=True,
        llm_provider_mode="remote_only",
        llm_remote_base_url="",
        llm_remote_api_key="",
    )
    assert provider_configuration_error(cfg) == "remote_not_configured"


def test_provider_configuration_error_remote_only_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_REMOTE_MODEL", raising=False)
    monkeypatch.delenv("LLM_TASK_MODEL_CHAT_REMOTE", raising=False)
    monkeypatch.delenv("LLM_TASK_MODEL_DRUNK_REMOTE", raising=False)
    monkeypatch.delenv("LLM_TASK_MODEL_REPEATER_FALLBACK_REMOTE", raising=False)
    monkeypatch.delenv("LLM_TASK_MODEL_REPEATER_POLISH_REMOTE", raising=False)
    cfg = Settings(
        llm_chat_enabled=True,
        llm_provider_mode="remote_only",
        llm_remote_base_url="https://api.example.com/v1",
        llm_remote_api_key="secret",
        llm_remote_model="",
        llm_task_model_chat_remote="",
        llm_task_model_drunk_remote="",
        llm_task_model_repeater_fallback_remote="",
        llm_task_model_repeater_polish_remote="",
    )
    assert provider_configuration_error(cfg) == "remote_model_not_configured"


def test_provider_configuration_error_remote_only_ok() -> None:
    cfg = Settings(
        llm_chat_enabled=True,
        llm_provider_mode="remote_only",
        llm_remote_base_url="https://api.example.com/v1",
        llm_remote_api_key="secret",
        llm_remote_model="gpt-4o-mini",
    )
    assert provider_configuration_error(cfg) is None


def test_provider_reachability_skips_unused_backends() -> None:
    cfg = Settings(llm_provider_mode="remote_only", llm_remote_base_url="", llm_remote_api_key="")
    reach = provider_reachability(cfg)
    assert reach["local_reachable"] is None
    assert reach["remote_reachable"] is None
