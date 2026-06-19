from __future__ import annotations

from typing import Any, Literal

from app.core.config import Settings, settings
from app.core.llm_backend_runtime import get_llm_model
from app.runtime_health import aggregate_llm_runtime_health, provider_row_health_state
from app.session import normalize_session_backend

from .categorizer import (
    categorizer_enabled,
    categorizer_model_name,
    needs_vision_for_request,
    request_tier_for_metadata,
)
from .local_backend import ping_local_provider_sync
from .registry import (
    load_provider_registry,
    local_base_url_for_spec,
    remote_is_configured,
)
from .registry import (
    providers_file_path as registry_providers_file_path,
)
from .remote_backend import ping_remote_provider_sync

ChainFailure = Literal["try_next", "fail"]

_DEFAULT_CHAIN_LOCAL_TASKS = frozenset({"llm_chat", "drunk"})
_DEFAULT_CHAIN_REMOTE_TASKS = frozenset({
    "repeater_fallback",
    "repeater_polish",
    "repeater_polish_lite",
    "repeater_select",
})


def parse_task_set(raw: str | None, default: frozenset[str]) -> frozenset[str]:
    text = str(raw or "").strip()
    if not text:
        return default
    tasks: set[str] = set()
    for part in text.replace(";", ",").split(","):
        item = part.strip().lower()
        if item:
            tasks.add(item)
    return frozenset(tasks) if tasks else default


def chain_local_tasks(cfg: Settings | None = None) -> frozenset[str]:
    c = cfg or settings
    return parse_task_set(c.llm_chain_local_tasks, _DEFAULT_CHAIN_LOCAL_TASKS)


def chain_remote_tasks(cfg: Settings | None = None) -> frozenset[str]:
    c = cfg or settings
    return parse_task_set(c.llm_chain_remote_tasks, _DEFAULT_CHAIN_REMOTE_TASKS)


def normalize_provider_mode(raw: str | None) -> Literal["local_only", "remote_only", "chain"]:
    value = str(raw or "local_only").strip().lower()
    if value in ("remote_only", "remote"):
        return "remote_only"
    if value == "chain":
        return "chain"
    return "local_only"


def normalize_chain_failure(raw: str | None) -> ChainFailure:
    value = str(raw or "try_next").strip().lower()
    if value in ("fail", "stop", "abort"):
        return "fail"
    return "try_next"


def parse_chain_order(raw: str | None, cfg: Settings | None = None) -> list[str]:
    registry = load_provider_registry(cfg)
    text = str(raw or "local,remote").strip().lower()
    order: list[str] = []
    for part in text.replace(";", ",").split(","):
        item = part.strip()
        if item in ("local", "ollama"):
            local_id = registry.legacy_local_id()
            if local_id not in order:
                order.append(local_id)
            continue
        if item == "remote":
            remote_id = registry.legacy_remote_id()
            if remote_id not in order:
                order.append(remote_id)
            continue
        if item and registry.get(item) and item not in order:
            order.append(item)
    if order:
        return order
    return [registry.legacy_local_id(), registry.legacy_remote_id()]


def local_is_required(cfg: Settings | None = None) -> bool:
    mode = normalize_provider_mode((cfg or settings).llm_provider_mode)
    return mode in ("local_only", "chain")


_DEFAULT_TIER_REMOTE_TASKS = frozenset({"llm_chat", "drunk"})
_VALID_MOE_TIERS = frozenset({"simple", "medium", "complex"})


def parse_tier_set(raw: str | None) -> frozenset[str]:
    text = str(raw or "").strip()
    if not text:
        return frozenset()
    tiers: set[str] = set()
    for part in text.replace(";", ",").split(","):
        item = part.strip().lower()
        if item in _VALID_MOE_TIERS:
            tiers.add(item)
    return frozenset(tiers)


def moe_tier_remote_tasks(cfg: Settings | None = None) -> frozenset[str]:
    c = cfg or settings
    return parse_task_set(c.llm_moe_tier_remote_tasks, _DEFAULT_TIER_REMOTE_TASKS)


def normalize_tier_remote_fallback(raw: str | None) -> Literal["local", "none"]:
    value = str(raw or "local").strip().lower()
    if value in ("none", "fail", "stop", "remote_only"):
        return "none"
    return "local"


def moe_tier_remote_routing_enabled(cfg: Settings | None = None) -> bool:
    c = cfg or settings
    return bool(parse_tier_set(c.llm_moe_tier_remote_tiers))


def resolve_tier_based_provider_order(
    *,
    task: str,
    user_text: str,
    metadata: dict[str, Any] | None,
    cfg: Settings | None = None,
) -> list[str] | None:
    c = cfg or settings
    remote_tiers = parse_tier_set(c.llm_moe_tier_remote_tiers)
    if not remote_tiers or not remote_is_configured(c):
        return None
    if task not in moe_tier_remote_tasks(c):
        return None

    tier = request_tier_for_metadata(user_text, metadata)
    if tier not in remote_tiers:
        return None

    registry = load_provider_registry(c)
    remote_ids = registry.filter_usable(registry.remote_provider_ids())
    if not remote_ids and registry.legacy_remote_usable():
        remote_ids = registry.filter_usable([registry.legacy_remote_id()])
    if not remote_ids:
        return None

    if normalize_tier_remote_fallback(c.llm_moe_tier_remote_fallback) == "none":
        return remote_ids

    local_ids = registry.filter_usable(registry.local_provider_ids())
    if not local_ids:
        local_ids = [registry.legacy_local_id()]
    order: list[str] = []
    for provider_id in (*remote_ids, *local_ids):
        if provider_id not in order:
            order.append(provider_id)
    return order


def resolve_provider_order(
    cfg: Settings | None = None,
    metadata: dict[str, Any] | None = None,
    user_text: str = "",
) -> list[str]:
    c = cfg or settings
    registry = load_provider_registry(c)
    task = infer_task(metadata)

    tier_order = resolve_tier_based_provider_order(
        task=task,
        user_text=user_text,
        metadata=metadata,
        cfg=c,
    )
    if tier_order:
        return tier_order

    mode = normalize_provider_mode(c.llm_provider_mode)

    if mode == "local_only":
        local_ids = registry.local_provider_ids()
        return registry.filter_usable(local_ids) or [registry.legacy_local_id()]
    if mode == "remote_only":
        remote_ids = registry.remote_provider_ids()
        if remote_ids:
            return registry.filter_usable(remote_ids)
        legacy = registry.legacy_remote_id()
        return registry.filter_usable([legacy])

    if mode == "chain":
        if registry.has_task_routing() and task in registry.task_routing:
            routed = registry.task_routing[task]
            usable = registry.filter_usable([routed])
            if usable:
                return usable

        remote_tasks = chain_remote_tasks(c)
        local_tasks = chain_local_tasks(c)
        if task in remote_tasks and registry.legacy_remote_usable():
            return [registry.legacy_remote_id()]
        if task in local_tasks:
            return [registry.legacy_local_id()]

        if registry.chain_fallback:
            usable = registry.filter_usable(registry.chain_fallback)
            if usable:
                return usable

    order = parse_chain_order(c.llm_chain_order, c)
    return registry.filter_usable(order) or [registry.legacy_local_id()]


def infer_task(metadata: dict[str, Any] | None) -> str:
    meta = metadata if isinstance(metadata, dict) else {}
    task = str(meta.get("task") or "").strip().lower()
    if task:
        return task
    mode = str(meta.get("mode") or "normal").strip().lower()
    if mode == "drunk":
        return "drunk"
    return "llm_chat"


def task_model_override(task: str, provider_id: str, cfg: Settings | None = None) -> str:
    c = cfg or settings
    registry = load_provider_registry(c)
    spec = registry.get(provider_id)
    if spec and spec.task_models.get(task):
        return spec.task_models[task]

    kind = registry.kind_of(provider_id)
    mapping = {
        ("llm_chat", "local"): c.llm_task_model_chat,
        ("llm_chat", "remote"): c.llm_task_model_chat_remote or c.llm_task_model_chat,
        ("drunk", "local"): c.llm_task_model_drunk,
        ("drunk", "remote"): c.llm_task_model_drunk_remote or c.llm_task_model_drunk,
        ("repeater_fallback", "local"): c.llm_task_model_repeater_fallback,
        ("repeater_fallback", "remote"): (
            c.llm_task_model_repeater_fallback_remote or c.llm_task_model_repeater_fallback
        ),
        ("repeater_polish", "local"): c.llm_task_model_repeater_polish,
        ("repeater_polish", "remote"): (c.llm_task_model_repeater_polish_remote or c.llm_task_model_repeater_polish),
        ("repeater_polish_lite", "local"): c.llm_task_model_repeater_polish_lite,
        ("repeater_polish_lite", "remote"): (
            c.llm_task_model_repeater_polish_lite_remote or c.llm_task_model_repeater_polish_lite
        ),
        ("repeater_select", "local"): c.llm_task_model_repeater_select,
        ("repeater_select", "remote"): (c.llm_task_model_repeater_select_remote or c.llm_task_model_repeater_select),
        ("affect_refine", "local"): c.persona_affect_refine_model,
        ("affect_refine", "remote"): c.llm_task_model_affect_refine_remote or c.persona_affect_refine_model,
    }
    return str(mapping.get((task, kind), "") or "").strip()


def moe_model_for_tier(tier: str, provider_id: str, cfg: Settings | None = None) -> str:
    c = cfg or settings
    registry = load_provider_registry(c)
    kind = registry.kind_of(provider_id)
    spec = registry.get(provider_id)
    if kind == "remote":
        mapping = {
            "simple": c.llm_moe_remote_model_simple,
            "medium": c.llm_moe_remote_model_medium,
            "complex": c.llm_moe_remote_model_complex,
        }
        fallback = (spec.default_model if spec else "") or c.llm_remote_model
    else:
        mapping = {
            "simple": c.llm_moe_model_simple,
            "medium": c.llm_moe_model_medium,
            "complex": c.llm_moe_model_complex,
        }
        fallback = (spec.default_model if spec else "") or get_llm_model()
    model = str(mapping.get(tier, "") or "").strip()
    return model or fallback


def vision_model_for_provider(provider_id: str, cfg: Settings | None = None) -> str:
    c = cfg or settings
    registry = load_provider_registry(c)
    if registry.kind_of(provider_id) == "remote":
        return (c.llm_moe_remote_model_vision or "").strip()
    return (c.llm_moe_model_vision or "").strip()


def moe_tier_routing_enabled(cfg: Settings | None = None) -> bool:
    c = cfg or settings
    if c.llm_moe_enabled:
        return True
    if str(c.llm_routing or "").strip().lower() == "moe":
        return True
    local_models = (
        c.llm_moe_model_simple,
        c.llm_moe_model_medium,
        c.llm_moe_model_complex,
    )
    remote_models = (
        c.llm_moe_remote_model_simple,
        c.llm_moe_remote_model_medium,
        c.llm_moe_remote_model_complex,
    )
    configured = [str(item or "").strip() for item in (*local_models, *remote_models) if str(item or "").strip()]
    return len(configured) >= 2


def resolve_model_name(
    *,
    provider: str,
    metadata: dict[str, Any] | None,
    user_text: str,
    request_model: str | None,
    cfg: Settings | None = None,
) -> str:
    c = cfg or settings
    provider_id = str(provider or "").strip() or "local"
    explicit = (request_model or "").strip()
    if explicit:
        return explicit

    meta = metadata if isinstance(metadata, dict) else {}
    task = infer_task(meta)
    task_model = task_model_override(task, provider_id, c)
    if task_model:
        return task_model

    if needs_vision_for_request(user_text, metadata=meta):
        vision_model = vision_model_for_provider(provider_id, c)
        if vision_model:
            return vision_model

    registry = load_provider_registry(c)
    spec = registry.get(provider_id)
    if moe_tier_routing_enabled(c):
        tier = request_tier_for_metadata(user_text, meta)
        moe_model = moe_model_for_tier(tier, provider_id, c)
        if moe_model:
            return moe_model

    if registry.kind_of(provider_id) == "remote":
        if spec and spec.default_model:
            return spec.default_model
        remote_model = (c.llm_remote_model or "").strip()
        if remote_model:
            return remote_model
        msg = f"remote model not configured for provider={provider_id}"
        raise ValueError(msg)

    if spec and spec.default_model:
        return spec.default_model
    return get_llm_model()


def provider_configuration_error(cfg: Settings | None = None) -> str | None:
    c = cfg or settings
    if not c.llm_chat_enabled:
        return None
    mode = normalize_provider_mode(c.llm_provider_mode)
    order = resolve_provider_order(c)
    if not order:
        if mode == "remote_only":
            return "remote_not_configured"
        return "no_provider_in_chain"
    registry = load_provider_registry(c)
    if mode == "remote_only":
        if not any(registry.is_usable(pid) for pid in order):
            return "remote_not_configured"
        if (
            not (c.llm_remote_model or "").strip()
            and not any(
                str(v or "").strip()
                for v in (
                    c.llm_task_model_chat_remote,
                    c.llm_task_model_drunk_remote,
                    c.llm_task_model_repeater_fallback_remote,
                    c.llm_task_model_repeater_polish_remote,
                    c.llm_task_model_repeater_select_remote,
                )
            )
            and not any(
                (registry.get(pid) and registry.get(pid).default_model)
                for pid in order
                if registry.kind_of(pid) == "remote"
            )
        ):
            return "remote_model_not_configured"
    if any(registry.kind_of(pid) == "remote" for pid in order) and not remote_is_configured(c):
        return "remote_not_configured"
    return None


def provider_status_rows(cfg: Settings | None = None) -> list[dict[str, Any]]:
    c = cfg or settings
    registry = load_provider_registry(c)
    rows: list[dict[str, Any]] = []
    for spec in sorted(registry.providers.values(), key=lambda item: item.id):
        base_url = local_base_url_for_spec(spec, c) if spec.kind == "local" else (spec.base_url or "")
        row: dict[str, Any] = {
            "id": spec.id,
            "kind": spec.kind,
            "enabled": spec.enabled,
            "configured": spec.is_configured(),
            "default_model": spec.default_model,
            "base_url": base_url,
            "reachable": None,
        }
        if spec.is_configured():
            if spec.kind == "local":
                row["reachable"] = ping_local_provider_sync(spec.id, timeout=2.0)
            else:
                row["reachable"] = ping_remote_provider_sync(spec.id, timeout=3.0, cfg=c)
        row["health_state"] = provider_row_health_state(
            configured=bool(row["configured"]),
            enabled=bool(row["enabled"]),
            reachable=row["reachable"],
        )
        row["circuit_state"] = "closed"
        rows.append(row)
    return rows


def provider_reachability(cfg: Settings | None = None) -> dict[str, bool | None]:
    c = cfg or settings
    registry = load_provider_registry(c)
    order = resolve_provider_order(c)
    local_reachable: bool | None = None
    remote_reachable: bool | None = None
    local_ids = [pid for pid in order if registry.kind_of(pid) == "local" and registry.is_usable(pid)]
    if local_ids and local_is_required(c):
        local_reachable = any(ping_local_provider_sync(pid, timeout=2.0) for pid in local_ids)
    remote_ids = [pid for pid in order if registry.kind_of(pid) == "remote" and registry.is_usable(pid)]
    if remote_ids:
        remote_reachable = any(ping_remote_provider_sync(pid, timeout=3.0, cfg=c) for pid in remote_ids)
    return {
        "local_reachable": local_reachable,
        "remote_reachable": remote_reachable,
    }


def llm_health_snapshot(cfg: Settings | None = None) -> dict[str, Any]:
    c = cfg or settings
    registry = load_provider_registry(c)
    mode = normalize_provider_mode(c.llm_provider_mode)
    config_error = provider_configuration_error(c)
    reachability = provider_reachability(c)
    provider_rows = provider_status_rows(c)
    aggregate = aggregate_llm_runtime_health(
        chat_enabled=bool(c.llm_chat_enabled),
        configuration_ok=config_error is None,
        provider_status=provider_rows,
    )
    return {
        "chat_enabled": bool(c.llm_chat_enabled),
        "provider_mode": mode,
        "chain_order": parse_chain_order(c.llm_chain_order, c),
        "active_providers": resolve_provider_order(c),
        "registered_providers": registry.snapshot(),
        "provider_status": provider_rows,
        "task_routing": dict(registry.task_routing),
        "providers_file": str(providers_file_path(c)),
        "remote_configured": remote_is_configured(c),
        "local_required": local_is_required(c),
        "configuration_ok": config_error is None,
        "configuration_error": config_error,
        "routing": str(c.llm_routing or "manual"),
        "moe_enabled": bool(c.llm_moe_enabled),
        "moe_tier_routing": moe_tier_routing_enabled(c),
        "moe_tier_remote_tiers": sorted(parse_tier_set(c.llm_moe_tier_remote_tiers)),
        "moe_tier_remote_tasks": sorted(moe_tier_remote_tasks(c)),
        "moe_tier_remote_fallback": normalize_tier_remote_fallback(c.llm_moe_tier_remote_fallback),
        "moe_model_vision": (c.llm_moe_model_vision or "").strip(),
        "moe_remote_model_vision": (c.llm_moe_remote_model_vision or "").strip(),
        "tools_enabled": bool(c.llm_tools_enabled),
        "tools_selective": bool(c.llm_tools_selective),
        "categorizer_enabled": categorizer_enabled(c),
        "categorizer_model": categorizer_model_name(c),
        "categorizer_provider": (c.llm_categorizer_provider or "local").strip() or "local",
        "session_backend": normalize_session_backend(c.llm_session_backend),
        "session_summary": {
            "enabled": bool(c.llm_session_summary_enabled),
            "threshold": int(c.llm_session_summary_threshold),
            "keep_messages": int(c.llm_session_summary_keep_messages),
        },
        **reachability,
        **aggregate,
    }


def providers_file_path(cfg: Settings | None = None):
    return registry_providers_file_path(cfg)
