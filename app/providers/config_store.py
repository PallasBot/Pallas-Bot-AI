"""providers.toml 读写。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from app.providers.registry import clear_provider_registry_cache, providers_file_path

if TYPE_CHECKING:
    from app.core.config import Settings


def load_providers_document(cfg: Settings | None = None) -> dict[str, Any]:
    path = providers_file_path(cfg)
    if not path.is_file():
        return {"providers": [], "routing": {"chain_fallback": [], "tasks": {}}}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    routing = data.get("routing")
    if not isinstance(routing, dict):
        routing = {}
    tasks = routing.get("tasks")
    if not isinstance(tasks, dict):
        tasks = {}
    chain_fallback = routing.get("chain_fallback")
    if not isinstance(chain_fallback, list):
        chain_fallback = []
    providers = data.get("providers")
    if not isinstance(providers, list):
        providers = []
    return {
        "providers": providers,
        "routing": {
            "chain_fallback": [str(item) for item in chain_fallback if str(item).strip()],
            "tasks": {str(k): str(v) for k, v in tasks.items() if str(k).strip() and str(v).strip()},
        },
        "providers_file": str(path),
    }


def export_providers_for_api(cfg: Settings | None = None) -> dict[str, Any]:
    doc = load_providers_document(cfg)
    providers: list[dict[str, Any]] = []
    for raw in doc.get("providers", []):
        if not isinstance(raw, dict):
            continue
        providers.append({
            "id": str(raw.get("id") or "").strip(),
            "kind": str(raw.get("kind") or "remote").strip().lower(),
            "base_url": str(raw.get("base_url") or "").strip(),
            "api_key_env": str(raw.get("api_key_env") or "").strip(),
            "default_model": str(raw.get("default_model") or "").strip(),
            "enabled": bool(raw.get("enabled", True)),
            "task_models": dict(raw.get("models") or raw.get("task_models") or {}),
        })
    return {
        "providers": providers,
        "routing": doc.get("routing", {}),
        "providers_file": doc.get("providers_file", str(providers_file_path(cfg))),
        "file_exists": Path(str(doc.get("providers_file", ""))).is_file(),
    }


def _toml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_providers_toml(document: dict[str, Any]) -> str:
    lines: list[str] = ["# 由 WebUI 保存生成"]
    providers = document.get("providers")
    if not isinstance(providers, list):
        providers = []
    for raw in providers:
        if not isinstance(raw, dict):
            continue
        provider_id = str(raw.get("id") or "").strip()
        if not provider_id:
            continue
        lines.extend([
            "",
            "[[providers]]",
            f"id = {_toml_quote(provider_id)}",
        ])
        kind = str(raw.get("kind") or "remote").strip().lower()
        lines.append(f"kind = {_toml_quote(kind)}")
        base_url = str(raw.get("base_url") or "").strip()
        if base_url:
            lines.append(f"base_url = {_toml_quote(base_url)}")
        api_key_env = str(raw.get("api_key_env") or "").strip()
        if api_key_env:
            lines.append(f"api_key_env = {_toml_quote(api_key_env)}")
        default_model = str(raw.get("default_model") or "").strip()
        if default_model:
            lines.append(f"default_model = {_toml_quote(default_model)}")
        if raw.get("enabled") is False:
            lines.append("enabled = false")
        task_models = raw.get("task_models")
        if isinstance(task_models, dict) and task_models:
            pairs = ", ".join(
                f"{_toml_quote(str(key))} = {_toml_quote(str(value))}"
                for key, value in task_models.items()
                if str(key).strip() and str(value).strip()
            )
            if pairs:
                lines.append(f"models = {{ {pairs} }}")

    routing = document.get("routing")
    if isinstance(routing, dict):
        chain_fallback = routing.get("chain_fallback")
        tasks = routing.get("tasks")
        has_routing = (isinstance(chain_fallback, list) and chain_fallback) or (isinstance(tasks, dict) and tasks)
        if has_routing:
            lines.extend(["", "[routing]"])
            if isinstance(chain_fallback, list) and chain_fallback:
                items = ", ".join(_toml_quote(str(item)) for item in chain_fallback if str(item).strip())
                if items:
                    lines.append(f"chain_fallback = [{items}]")
            if isinstance(tasks, dict) and tasks:
                lines.extend(["", "[routing.tasks]"])
                for key, value in tasks.items():
                    task = str(key or "").strip()
                    provider_id = str(value or "").strip()
                    if task and provider_id:
                        lines.append(f"{task} = {_toml_quote(provider_id)}")
    lines.append("")
    return "\n".join(lines)


def save_providers_document(document: dict[str, Any], cfg: Settings | None = None) -> Path:
    path = providers_file_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_providers_toml(document), encoding="utf-8")
    clear_provider_registry_cache()
    return path
