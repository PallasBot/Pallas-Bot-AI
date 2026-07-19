from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.providers.local_routing_config import export_local_routing_config, save_local_routing_config


def test_save_local_routing_config_updates_env_file_and_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join([
            "LLM_MODEL=old-model",
            "LLM_LOCAL_MULTI_MODEL_ENABLED=false",
            "LLM_MOE_MODEL_SIMPLE=qwen2.5:0.5b",
            "LLM_TASK_MODEL_REPEATER_SELECT=old-select",
            "",
        ]),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    cfg = Settings(
        llm_model="old-model",
        llm_local_multi_model_enabled=False,
        llm_moe_model_simple="qwen2.5:0.5b",
        llm_task_model_repeater_select="old-select",
    )
    monkeypatch.setattr("app.providers.local_routing_config.settings", cfg)

    saved = save_local_routing_config({
        "llm_model": "qwen3:8b",
        "local_multi_model_enabled": True,
        "moe_models": {
            "simple": "qwen2.5:0.5b",
            "medium": "qwen2.5:7b",
            "complex": "qwen3.5:9b",
            "vision": "",
        },
        "task_models": {
            "llm_chat": "",
            "drunk": "",
            "repeater_fallback": "",
            "repeater_polish": "",
            "repeater_polish_lite": "qwen2.5:0.5b",
            "repeater_select": "",
        },
    })

    text = env_file.read_text(encoding="utf-8")
    assert "LLM_MODEL=qwen3:8b" in text
    assert "LLM_LOCAL_MULTI_MODEL_ENABLED=true" in text
    assert "LLM_MOE_MODEL_MEDIUM=qwen2.5:7b" in text
    assert "LLM_MOE_MODEL_COMPLEX=qwen3.5:9b" in text
    assert "LLM_TASK_MODEL_REPEATER_POLISH_LITE=qwen2.5:0.5b" in text
    assert "LLM_TASK_MODEL_REPEATER_SELECT=" not in text
    assert cfg.llm_model == "qwen3:8b"
    assert cfg.llm_local_multi_model_enabled is True
    assert cfg.llm_moe_model_medium == "qwen2.5:7b"
    assert cfg.llm_task_model_repeater_polish_lite == "qwen2.5:0.5b"
    assert saved["llm_model"] == "qwen3:8b"
    assert saved["local_multi_model_enabled"] is True


def test_export_local_routing_config_uses_settings_values() -> None:
    cfg = Settings(
        llm_model="qwen3:8b",
        llm_local_multi_model_enabled=True,
        llm_moe_model_simple="qwen2.5:0.5b",
        llm_moe_model_medium="qwen2.5:7b",
        llm_moe_model_complex="qwen3.5:9b",
        llm_task_model_repeater_select="qwen2.5:0.5b",
    )

    payload = export_local_routing_config(cfg)

    assert payload["llm_model"] == "qwen3:8b"
    assert payload["local_multi_model_enabled"] is True
    assert payload["moe_models"]["medium"] == "qwen2.5:7b"
    assert payload["task_models"]["repeater_select"] == "qwen2.5:0.5b"
