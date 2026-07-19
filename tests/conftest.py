from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import settings
from app.providers.registry import clear_provider_registry_cache

# 隔离本机 config/providers.toml 与 API Bearer，避免污染单元测试。
_ISOLATED_PROVIDERS = Path(__file__).resolve().parent / "_fixtures" / "empty_providers.toml"


@pytest.fixture(autouse=True)
def isolate_provider_config(monkeypatch: pytest.MonkeyPatch) -> None:
    _ISOLATED_PROVIDERS.parent.mkdir(parents=True, exist_ok=True)
    if not _ISOLATED_PROVIDERS.exists():
        _ISOLATED_PROVIDERS.write_text("", encoding="utf-8")
    monkeypatch.setenv("LLM_PROVIDERS_FILE", str(_ISOLATED_PROVIDERS))
    monkeypatch.setattr(settings, "llm_providers_file", str(_ISOLATED_PROVIDERS))
    monkeypatch.setattr(settings, "api_bearer_token", "")
    # CI 无 Redis：默认走内存会话，避免连 localhost:6379
    monkeypatch.setattr(settings, "llm_session_backend", "memory")
    clear_provider_registry_cache()
    yield
    clear_provider_registry_cache()
