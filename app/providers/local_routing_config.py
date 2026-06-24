from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.config import Settings, settings

_ENV_FILE = Path(".env")

FIELD_TO_ENV: dict[str, str] = {
    "llm_model": "LLM_MODEL",
    "llm_local_multi_model_enabled": "LLM_LOCAL_MULTI_MODEL_ENABLED",
    "llm_moe_model_simple": "LLM_MOE_MODEL_SIMPLE",
    "llm_moe_model_medium": "LLM_MOE_MODEL_MEDIUM",
    "llm_moe_model_complex": "LLM_MOE_MODEL_COMPLEX",
    "llm_moe_model_vision": "LLM_MOE_MODEL_VISION",
    "llm_task_model_chat": "LLM_TASK_MODEL_CHAT",
    "llm_task_model_drunk": "LLM_TASK_MODEL_DRUNK",
    "llm_task_model_repeater_fallback": "LLM_TASK_MODEL_REPEATER_FALLBACK",
    "llm_task_model_repeater_polish": "LLM_TASK_MODEL_REPEATER_POLISH",
    "llm_task_model_repeater_polish_lite": "LLM_TASK_MODEL_REPEATER_POLISH_LITE",
    "llm_task_model_repeater_select": "LLM_TASK_MODEL_REPEATER_SELECT",
}


def export_local_routing_config(cfg: Settings | None = None) -> dict[str, Any]:
    c = cfg or settings
    return {
        "llm_model": str(c.llm_model or "").strip(),
        "local_multi_model_enabled": bool(c.llm_local_multi_model_enabled),
        "moe_models": {
            "simple": str(c.llm_moe_model_simple or "").strip(),
            "medium": str(c.llm_moe_model_medium or "").strip(),
            "complex": str(c.llm_moe_model_complex or "").strip(),
            "vision": str(c.llm_moe_model_vision or "").strip(),
        },
        "task_models": {
            "llm_chat": str(c.llm_task_model_chat or "").strip(),
            "drunk": str(c.llm_task_model_drunk or "").strip(),
            "repeater_fallback": str(c.llm_task_model_repeater_fallback or "").strip(),
            "repeater_polish": str(c.llm_task_model_repeater_polish or "").strip(),
            "repeater_polish_lite": str(c.llm_task_model_repeater_polish_lite or "").strip(),
            "repeater_select": str(c.llm_task_model_repeater_select or "").strip(),
        },
        "env_file": str(_ENV_FILE.resolve()),
    }


def _serialize_env_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text or None


def _quote_env(value: str) -> str:
    if not value:
        return ""
    if any(ch.isspace() for ch in value) or "#" in value or '"' in value:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _write_env_keys(updates: dict[str, str | None]) -> None:
    lines = _ENV_FILE.read_text(encoding="utf-8").splitlines() if _ENV_FILE.is_file() else []
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key, _sep, _rest = line.partition("=")
        key_s = key.strip()
        if key_s not in updates:
            out.append(line)
            continue
        seen.add(key_s)
        value = updates[key_s]
        if value is None:
            continue
        out.append(f"{key_s}={_quote_env(value)}")
    for key, value in updates.items():
        if key in seen or value is None:
            continue
        out.append(f"{key}={_quote_env(value)}")
    text = "\n".join(out).rstrip() + "\n"
    _ENV_FILE.write_text(text, encoding="utf-8")


def _apply_runtime_values(values: dict[str, Any]) -> None:
    for field_name, value in values.items():
        env_key = FIELD_TO_ENV[field_name]
        serialized = _serialize_env_value(value)
        if serialized is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = serialized
        setattr(settings, field_name, value)


def save_local_routing_config(document: dict[str, Any]) -> dict[str, Any]:
    llm_model = str(document.get("llm_model") or "").strip()
    if not llm_model:
        raise ValueError("默认本地模型不能为空")

    moe_raw = document.get("moe_models")
    moe_models = moe_raw if isinstance(moe_raw, dict) else {}
    task_raw = document.get("task_models")
    task_models = task_raw if isinstance(task_raw, dict) else {}

    values: dict[str, Any] = {
        "llm_model": llm_model,
        "llm_local_multi_model_enabled": bool(document.get("local_multi_model_enabled")),
        "llm_moe_model_simple": str(moe_models.get("simple") or "").strip(),
        "llm_moe_model_medium": str(moe_models.get("medium") or "").strip(),
        "llm_moe_model_complex": str(moe_models.get("complex") or "").strip(),
        "llm_moe_model_vision": str(moe_models.get("vision") or "").strip(),
        "llm_task_model_chat": str(task_models.get("llm_chat") or "").strip(),
        "llm_task_model_drunk": str(task_models.get("drunk") or "").strip(),
        "llm_task_model_repeater_fallback": str(task_models.get("repeater_fallback") or "").strip(),
        "llm_task_model_repeater_polish": str(task_models.get("repeater_polish") or "").strip(),
        "llm_task_model_repeater_polish_lite": str(task_models.get("repeater_polish_lite") or "").strip(),
        "llm_task_model_repeater_select": str(task_models.get("repeater_select") or "").strip(),
    }
    env_updates = {FIELD_TO_ENV[field_name]: _serialize_env_value(value) for field_name, value in values.items()}
    _write_env_keys(env_updates)
    _apply_runtime_values(values)
    return export_local_routing_config()
