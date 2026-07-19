from __future__ import annotations

from app.core.config import Settings
from app.providers.config_store import export_providers_for_api, save_providers_document
from app.providers.registry import clear_provider_registry_cache, load_provider_registry


def test_render_and_save_providers_toml(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.chdir(tmp_path)
    clear_provider_registry_cache()
    document = {
        "providers": [
            {
                "id": "local",
                "kind": "local",
                "default_model": "qwen2.5:7b",
                "enabled": True,
            },
            {
                "id": "deepseek",
                "kind": "remote",
                "base_url": "https://api.deepseek.com",
                "api_key_env": "LLM_REMOTE_API_KEY",
                "default_model": "deepseek-v4-flash",
            },
        ],
        "routing": {
            "chain_fallback": ["local", "deepseek"],
            "tasks": {"llm_chat": "local", "repeater_polish": "deepseek"},
        },
    }
    path = save_providers_document(document, Settings(llm_providers_file=str(config_dir / "providers.toml")))
    text = path.read_text(encoding="utf-8")
    assert "[[providers]]" in text
    assert 'llm_chat = "local"' in text
    registry = load_provider_registry(Settings(llm_providers_file=str(path)))
    assert registry.task_routing["llm_chat"] == "local"


def test_save_inline_api_key_and_preserve_on_empty_resubmit(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.chdir(tmp_path)
    clear_provider_registry_cache()
    settings = Settings(llm_providers_file=str(config_dir / "providers.toml"))
    document = {
        "providers": [
            {
                "id": "remote",
                "kind": "remote",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-test-secret-key",
                "default_model": "deepseek-v4-flash",
            },
        ],
        "routing": {"chain_fallback": ["remote"], "tasks": {"llm_chat": "remote"}},
    }
    save_providers_document(document, settings)
    text = (config_dir / "providers.toml").read_text(encoding="utf-8")
    assert 'api_key = "sk-test-secret-key"' in text

    exported = export_providers_for_api(settings)
    assert exported["providers"][0]["api_key_set"] is True
    assert "api_key" not in exported["providers"][0]

    resubmit = {
        "providers": [
            {
                "id": "remote",
                "kind": "remote",
                "base_url": "https://api.deepseek.com",
                "default_model": "deepseek-v4-flash",
            },
        ],
        "routing": {"chain_fallback": ["remote"], "tasks": {"llm_chat": "remote"}},
    }
    save_providers_document(resubmit, settings)
    text2 = (config_dir / "providers.toml").read_text(encoding="utf-8")
    assert 'api_key = "sk-test-secret-key"' in text2


def test_migrate_pasted_api_key_from_api_key_env(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.chdir(tmp_path)
    clear_provider_registry_cache()
    settings = Settings(llm_providers_file=str(config_dir / "providers.toml"))
    document = {
        "providers": [
            {
                "id": "remote",
                "kind": "remote",
                "base_url": "https://api.deepseek.com",
                "api_key_env": "sk-pasted-by-mistake",
                "default_model": "deepseek-v4-flash",
            },
        ],
        "routing": {"chain_fallback": ["remote"], "tasks": {}},
    }
    save_providers_document(document, settings)
    text = (config_dir / "providers.toml").read_text(encoding="utf-8")
    assert 'api_key = "sk-pasted-by-mistake"' in text
    assert "api_key_env" not in text
