from collections.abc import Callable
from importlib import import_module

from fastapi import APIRouter

from app.core.celery import celery_task_package_enabled
from app.core.logger import logger

# LLM 栈默认可用的 HTTP 端点（不依赖 sing/tts/chat 可选依赖组）
LLM_CORE_ENDPOINTS = frozenset({
    "embeddings",
    "images",
    "llm_chat",
    "llm_manage",
    "llm_providers",
    "llm_stats",
    "media_assets",
    "media_tasks",
    "ops_logs",
    "persona_affect",
})

# 可选任务包 → 额外挂载的路由名
_PACKAGE_EXTRA_ENDPOINTS: dict[str, frozenset[str]] = {
    "chat": frozenset({"chat"}),
    "sing": frozenset({"sing", "ncm_login"}),
    "tts": frozenset({"tts"}),
}

DEFAULT_ENDPOINTS = frozenset().union(LLM_CORE_ENDPOINTS, *(_PACKAGE_EXTRA_ENDPOINTS.values()))


def resolve_enabled_endpoints(
    enabled_endpoints: set[str] | frozenset[str] | None = None,
) -> frozenset[str]:
    """按 CELERY_TASK_PACKAGES 裁剪默认路由；显式传入时原样使用。"""
    if enabled_endpoints is not None:
        return frozenset(enabled_endpoints)
    selected = set(LLM_CORE_ENDPOINTS)
    for package, names in _PACKAGE_EXTRA_ENDPOINTS.items():
        if celery_task_package_enabled(package):
            selected.update(names)
    return frozenset(selected)


def _load_sing() -> APIRouter:
    return import_module("app.api.endpoints.sing").router


def _load_chat() -> APIRouter:
    return import_module("app.api.endpoints.chat").router


def _load_embeddings() -> APIRouter:
    return import_module("app.api.endpoints.embeddings").router


def _load_images() -> APIRouter:
    return import_module("app.api.endpoints.images").router


def _load_media_tasks() -> APIRouter:
    return import_module("app.api.endpoints.media_tasks").router


def _load_media_assets() -> APIRouter:
    return import_module("app.api.endpoints.media_assets").router


def _load_llm_chat() -> APIRouter:
    return import_module("app.api.endpoints.llm_chat").router


def _load_llm_stats() -> APIRouter:
    return import_module("app.api.endpoints.llm_stats").router


def _load_llm_manage() -> tuple[APIRouter, APIRouter]:
    module = import_module("app.api.endpoints.llm_manage")
    return module.router, module.legacy_router


def _load_llm_providers() -> APIRouter:
    return import_module("app.api.endpoints.llm_providers").router


def _load_tts() -> APIRouter:
    return import_module("app.api.endpoints.tts").router


def _load_ncm_login() -> APIRouter:
    return import_module("app.api.endpoints.ncm_login").router


def _load_persona_affect() -> APIRouter:
    return import_module("app.api.endpoints.persona_affect").router


def _load_ops_logs() -> APIRouter:
    return import_module("app.api.endpoints.ops_logs").router


ENDPOINT_LOADERS: dict[str, Callable[[], APIRouter | tuple[APIRouter, ...]]] = {
    "sing": _load_sing,
    "chat": _load_chat,
    "embeddings": _load_embeddings,
    "images": _load_images,
    "media_tasks": _load_media_tasks,
    "media_assets": _load_media_assets,
    "llm_chat": _load_llm_chat,
    "llm_stats": _load_llm_stats,
    "llm_manage": _load_llm_manage,
    "llm_providers": _load_llm_providers,
    "tts": _load_tts,
    "ncm_login": _load_ncm_login,
    "ops_logs": _load_ops_logs,
    "persona_affect": _load_persona_affect,
}


def build_api_router(enabled_endpoints: set[str] | frozenset[str]) -> APIRouter:
    router = APIRouter()
    for endpoint_name in sorted(enabled_endpoints):
        loader = ENDPOINT_LOADERS.get(endpoint_name)
        if loader is None:
            continue
        try:
            loaded = loader()
        except ImportError as exc:
            logger.warning("跳过路由 {}：缺少可选依赖 ({})", endpoint_name, exc)
            continue
        if isinstance(loaded, tuple):
            for sub_router in loaded:
                router.include_router(sub_router)
            continue
        router.include_router(loaded)
    return router
