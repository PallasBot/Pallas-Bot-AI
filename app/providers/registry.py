"""LLM 提供方注册表。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from app.core.config import Settings, settings

ProviderKind = Literal["local", "remote"]

_CACHE: ProviderRegistry | None = None
_CACHE_KEY: tuple[Any, ...] | None = None


def registry_cache_key(cfg: Settings) -> tuple[Any, ...]:
    path = providers_file_path(cfg)
    mtime = path.stat().st_mtime if path.is_file() else 0.0
    return (
        mtime,
        str(cfg.llm_providers_file or ""),
        str(cfg.llm_remote_base_url or ""),
        str(cfg.llm_remote_api_key or ""),
        str(cfg.llm_remote_model or ""),
    )


@dataclass(frozen=True)
class LlmProviderSpec:
    id: str
    kind: ProviderKind
    base_url: str = ""
    api_key: str = ""
    default_model: str = ""
    enabled: bool = True
    task_models: dict[str, str] = field(default_factory=dict)

    def is_configured(self) -> bool:
        if not self.enabled:
            return False
        if self.kind == "local":
            if self.id == "local":
                return True
            return bool(self.base_url.strip())
        return bool(self.base_url.strip() and self.api_key.strip())


@dataclass
class ProviderRegistry:
    providers: dict[str, LlmProviderSpec]
    task_routing: dict[str, str]
    chain_fallback: list[str]

    def get(self, provider_id: str) -> LlmProviderSpec | None:
        return self.providers.get(provider_id)

    def kind_of(self, provider_id: str) -> ProviderKind:
        spec = self.get(provider_id)
        if spec is not None:
            return spec.kind
        if provider_id == "remote":
            return "remote"
        return "local"

    def has_task_routing(self) -> bool:
        return bool(self.task_routing)

    def remote_provider_ids(self) -> list[str]:
        return [spec.id for spec in self.providers.values() if spec.kind == "remote" and spec.is_configured()]

    def local_provider_ids(self) -> list[str]:
        return [spec.id for spec in self.providers.values() if spec.kind == "local" and spec.is_configured()]

    def legacy_local_id(self) -> str:
        if "local" in self.providers and self.providers["local"].is_configured():
            return "local"
        locals_ids = self.local_provider_ids()
        return locals_ids[0] if locals_ids else "local"

    def legacy_remote_id(self) -> str:
        if "remote" in self.providers and self.providers["remote"].is_configured():
            return "remote"
        remotes = self.remote_provider_ids()
        return remotes[0] if remotes else "remote"

    def legacy_remote_usable(self) -> bool:
        spec = self.get(self.legacy_remote_id())
        return bool(spec and spec.is_configured())

    def is_usable(self, provider_id: str) -> bool:
        spec = self.get(provider_id)
        return bool(spec and spec.is_configured())

    def filter_usable(self, provider_ids: list[str]) -> list[str]:
        out: list[str] = []
        for provider_id in provider_ids:
            if self.is_usable(provider_id) and provider_id not in out:
                out.append(provider_id)
        return out

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "id": spec.id,
                "kind": spec.kind,
                "enabled": spec.enabled,
                "configured": spec.is_configured(),
                "default_model": spec.default_model,
                "base_url": spec.base_url,
                "task_models": dict(spec.task_models),
            }
            for spec in sorted(self.providers.values(), key=lambda item: item.id)
        ]


def providers_file_path(cfg: Settings | None = None) -> Path:
    c = cfg or settings
    raw = (c.llm_providers_file or "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        return path
    return Path.cwd() / "config" / "providers.toml"


def clear_provider_registry_cache() -> None:
    global _CACHE, _CACHE_KEY
    _CACHE = None
    _CACHE_KEY = None


def _read_api_key(raw: dict[str, Any]) -> str:
    inline = str(raw.get("api_key") or "").strip()
    if inline:
        return inline
    env_name = str(raw.get("api_key_env") or "").strip()
    if env_name:
        return str(os.environ.get(env_name) or "").strip()
    return ""


def _parse_task_models(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        task = str(key or "").strip().lower()
        model = str(value or "").strip()
        if task and model:
            out[task] = model
    return out


def _parse_providers_from_toml(data: dict[str, Any]) -> dict[str, LlmProviderSpec]:
    providers: dict[str, LlmProviderSpec] = {}
    rows = data.get("providers")
    if not isinstance(rows, list):
        return providers
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        provider_id = str(raw.get("id") or "").strip()
        if not provider_id:
            continue
        kind = str(raw.get("kind") or "remote").strip().lower()
        provider_kind: ProviderKind = "local" if kind == "local" else "remote"
        models_raw = raw.get("models")
        if not isinstance(models_raw, dict):
            models_raw = raw.get("task_models")
        providers[provider_id] = LlmProviderSpec(
            id=provider_id,
            kind=provider_kind,
            base_url=str(raw.get("base_url") or "").strip(),
            api_key=_read_api_key(raw),
            default_model=str(raw.get("default_model") or "").strip(),
            enabled=bool(raw.get("enabled", True)),
            task_models=_parse_task_models(models_raw),
        )
    return providers


def _parse_routing_from_toml(data: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    routing = data.get("routing")
    if not isinstance(routing, dict):
        return {}, []
    task_routing: dict[str, str] = {}
    tasks = routing.get("tasks")
    if isinstance(tasks, dict):
        for key, value in tasks.items():
            task = str(key or "").strip().lower()
            provider_id = str(value or "").strip()
            if task and provider_id:
                task_routing[task] = provider_id
    chain_fallback: list[str] = []
    fallback = routing.get("chain_fallback")
    if isinstance(fallback, list):
        for item in fallback:
            provider_id = str(item or "").strip()
            if provider_id and provider_id not in chain_fallback:
                chain_fallback.append(provider_id)
    return task_routing, chain_fallback


def _legacy_registry(cfg: Settings) -> ProviderRegistry:
    providers: dict[str, LlmProviderSpec] = {
        "local": LlmProviderSpec(id="local", kind="local"),
    }
    base_url = (cfg.llm_remote_base_url or "").strip()
    api_key = (cfg.llm_remote_api_key or "").strip()
    default_model = (cfg.llm_remote_model or "").strip()
    if base_url and api_key:
        providers["remote"] = LlmProviderSpec(
            id="remote",
            kind="remote",
            base_url=base_url,
            api_key=api_key,
            default_model=default_model,
        )
    return ProviderRegistry(providers=providers, task_routing={}, chain_fallback=[])


def _merge_legacy_remote(registry: ProviderRegistry, cfg: Settings) -> ProviderRegistry:
    if registry.get("remote") or not (cfg.llm_remote_base_url and cfg.llm_remote_api_key):
        return registry
    legacy = _legacy_registry(cfg).providers.get("remote")
    if legacy is None:
        return registry
    merged = dict(registry.providers)
    merged["remote"] = legacy
    return ProviderRegistry(
        providers=merged,
        task_routing=registry.task_routing,
        chain_fallback=registry.chain_fallback,
    )


def load_provider_registry(cfg: Settings | None = None) -> ProviderRegistry:
    global _CACHE, _CACHE_KEY
    c = cfg or settings
    cache_key = registry_cache_key(c)
    if _CACHE is not None and cache_key == _CACHE_KEY:
        return _CACHE

    path = providers_file_path(c)

    if path.is_file():
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        providers = _parse_providers_from_toml(data)
        if "local" not in providers:
            providers["local"] = LlmProviderSpec(id="local", kind="local")
        task_routing, chain_fallback = _parse_routing_from_toml(data)
        registry = ProviderRegistry(
            providers=providers,
            task_routing=task_routing,
            chain_fallback=chain_fallback,
        )
        registry = _merge_legacy_remote(registry, c)
    else:
        registry = _legacy_registry(c)

    _CACHE = registry
    _CACHE_KEY = cache_key
    return registry


def remote_is_configured(cfg: Settings | None = None) -> bool:
    registry = load_provider_registry(cfg)
    return registry.legacy_remote_usable() or bool(registry.remote_provider_ids())


def local_base_url_for_spec(spec: LlmProviderSpec, cfg: Settings | None = None) -> str:
    url = (spec.base_url or "").strip().rstrip("/")
    if url:
        return url
    if spec.id == "local":
        return (cfg or settings).llm_backend_url.rstrip("/")
    return ""


def provider_spec_or_error(provider_id: str, cfg: Settings | None = None) -> LlmProviderSpec:
    registry = load_provider_registry(cfg)
    spec = registry.get(provider_id)
    if spec is None:
        msg = f"unknown provider: {provider_id}"
        raise ValueError(msg)
    if not spec.is_configured():
        msg = f"provider not configured: {provider_id}"
        raise ValueError(msg)
    return spec
