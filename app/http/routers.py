from collections.abc import Callable
from importlib import import_module

from fastapi import APIRouter

from app.core.celery import celery_task_package_enabled
from app.core.logger import logger

MEDIA_CORE_ENDPOINTS = frozenset({
    "media_assets",
    "media_models",
    "media_tasks",
    "ops_logs",
})

_PACKAGE_EXTRA_ENDPOINTS: dict[str, frozenset[str]] = {
    "chat": frozenset({"chat"}),
    "sing": frozenset({"sing", "ncm_login"}),
    "tts": frozenset({"tts"}),
}

DEFAULT_ENDPOINTS = frozenset().union(MEDIA_CORE_ENDPOINTS, *(_PACKAGE_EXTRA_ENDPOINTS.values()))


def resolve_enabled_endpoints(
    enabled_endpoints: set[str] | frozenset[str] | None = None,
) -> frozenset[str]:
    """按 CELERY_TASK_PACKAGES 裁剪默认路由；显式传入时原样使用。"""
    if enabled_endpoints is not None:
        return frozenset(enabled_endpoints)
    selected = set(MEDIA_CORE_ENDPOINTS)
    for package, names in _PACKAGE_EXTRA_ENDPOINTS.items():
        if celery_task_package_enabled(package):
            selected.update(names)
    return frozenset(selected)


def _load_sing() -> APIRouter:
    return import_module("app.http.endpoints.sing").router


def _load_chat() -> APIRouter:
    return import_module("app.http.endpoints.chat").router


def _load_media_tasks() -> APIRouter:
    return import_module("app.http.endpoints.media_tasks").router


def _load_media_assets() -> APIRouter:
    return import_module("app.http.endpoints.media_assets").router


def _load_media_models() -> APIRouter:
    return import_module("app.http.endpoints.media_models").router


def _load_tts() -> APIRouter:
    return import_module("app.http.endpoints.tts").router


def _load_ncm_login() -> APIRouter:
    return import_module("app.http.endpoints.ncm_login").router


def _load_ops_logs() -> APIRouter:
    return import_module("app.http.endpoints.ops_logs").router


ENDPOINT_LOADERS: dict[str, Callable[[], APIRouter | tuple[APIRouter, ...]]] = {
    "sing": _load_sing,
    "chat": _load_chat,
    "media_tasks": _load_media_tasks,
    "media_assets": _load_media_assets,
    "media_models": _load_media_models,
    "tts": _load_tts,
    "ncm_login": _load_ncm_login,
    "ops_logs": _load_ops_logs,
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
            logger.warning("skipping route {}: missing optional dependency ({})", endpoint_name, exc)
            continue
        if isinstance(loaded, tuple):
            for sub_router in loaded:
                router.include_router(sub_router)
            continue
        router.include_router(loaded)
    return router
