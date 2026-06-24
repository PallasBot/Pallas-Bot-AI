from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.providers.registry import (
    LlmProviderSpec,
    clear_provider_registry_cache,
    load_provider_registry,
    local_base_url_for_spec,
)
from app.providers.router import resolve_model_name, resolve_provider_order


@pytest.fixture(autouse=True)
def reset_registry_cache() -> None:
    clear_provider_registry_cache()
    yield
    clear_provider_registry_cache()


def test_legacy_env_single_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "config" / "providers.toml"
    monkeypatch.chdir(tmp_path)
    cfg = Settings(
        llm_providers_file=str(missing),
        llm_remote_base_url="https://api.deepseek.com",
        llm_remote_api_key="secret",
        llm_remote_model="deepseek-chat",
        llm_provider_mode="chain",
        llm_chain_remote_tasks="llm_chat",
    )
    assert resolve_provider_order(cfg, {"task": "llm_chat"}) == ["remote"]


def test_multi_remote_task_routing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    providers_file = config_dir / "providers.toml"
    providers_file.write_text(
        """
[[providers]]
id = "local"
kind = "local"

[[providers]]
id = "deepseek"
kind = "remote"
base_url = "https://api.deepseek.com"
api_key = "k1"
default_model = "deepseek-chat"

[[providers]]
id = "deepseek-flash"
kind = "remote"
base_url = "https://api.deepseek.com"
api_key = "k2"
default_model = "deepseek-v4-flash"

[routing.tasks]
llm_chat = "deepseek"
repeater_polish = "deepseek-flash"
repeater_fallback = "local"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    cfg = Settings(
        llm_providers_file=str(providers_file),
        llm_provider_mode="chain",
    )
    assert resolve_provider_order(cfg, {"task": "llm_chat"}) == ["deepseek"]
    assert resolve_provider_order(cfg, {"task": "repeater_polish"}) == ["deepseek-flash"]
    assert resolve_provider_order(cfg, {"task": "repeater_fallback"}) == ["local"]


def test_provider_task_model_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    providers_file = config_dir / "providers.toml"
    providers_file.write_text(
        """
[[providers]]
id = "deepseek"
kind = "remote"
base_url = "https://api.deepseek.com"
api_key = "k1"
default_model = "default-remote"
models = { llm_chat = "chat-model" }
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    cfg = Settings(llm_providers_file=str(providers_file))
    model = resolve_model_name(
        provider="deepseek",
        metadata={"task": "llm_chat"},
        user_text="你好",
        request_model=None,
        cfg=cfg,
    )
    assert model == "chat-model"


def test_registry_snapshot_lists_providers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    providers_file = config_dir / "providers.toml"
    providers_file.write_text(
        """
[[providers]]
id = "local"
kind = "local"
[[providers]]
id = "deepseek"
kind = "remote"
base_url = "https://api.deepseek.com"
api_key = "k1"
default_model = "deepseek-chat"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    registry = load_provider_registry(Settings(llm_providers_file=str(providers_file)))
    assert {row["id"] for row in registry.snapshot()} == {"local", "deepseek"}


def test_multi_local_task_routing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    providers_file = config_dir / "providers.toml"
    providers_file.write_text(
        """
[[providers]]
id = "local"
kind = "local"
default_model = "qwen2.5:7b"

[[providers]]
id = "ollama-tools"
kind = "local"
base_url = "http://127.0.0.1:11435"
default_model = "qwen2.5-tools"

[routing.tasks]
llm_chat = "ollama-tools"
repeater_fallback = "local"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    cfg = Settings(
        llm_providers_file=str(providers_file),
        llm_provider_mode="chain",
        llm_model="global-model",
        llm_moe_model_simple="",
        llm_moe_model_medium="",
        llm_moe_model_complex="",
    )
    assert resolve_provider_order(cfg, {"task": "llm_chat"}) == ["ollama-tools"]
    assert resolve_provider_order(cfg, {"task": "repeater_fallback"}) == ["local"]
    model = resolve_model_name(
        provider="ollama-tools",
        metadata={"task": "llm_chat"},
        user_text="你好",
        request_model=None,
        cfg=cfg,
    )
    assert model == "qwen2.5-tools"


def test_local_base_url_for_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Settings(llm_backend_url="http://127.0.0.1:11434")
    assert local_base_url_for_spec(LlmProviderSpec(id="local", kind="local"), cfg) == "http://127.0.0.1:11434"
    assert (
        local_base_url_for_spec(
            LlmProviderSpec(id="ollama-tools", kind="local", base_url="http://127.0.0.1:11435"),
            cfg,
        )
        == "http://127.0.0.1:11435"
    )
    assert not local_base_url_for_spec(LlmProviderSpec(id="ollama-tools", kind="local"), cfg)
