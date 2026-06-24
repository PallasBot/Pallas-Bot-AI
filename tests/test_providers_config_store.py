from __future__ import annotations

from app.core.config import Settings
from app.providers.config_store import save_providers_document
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
