from collections.abc import Callable
from importlib import import_module

from fastapi import APIRouter

DEFAULT_ENDPOINTS = frozenset({
    "chat",
    "images",
    "llm_chat",
    "llm_manage",
    "llm_stats",
    "media_tasks",
    "ncm_login",
    "persona_affect",
    "sing",
    "tts",
})


def _load_sing() -> APIRouter:
    return import_module("app.api.endpoints.sing").router


def _load_chat() -> APIRouter:
    return import_module("app.api.endpoints.chat").router


def _load_images() -> APIRouter:
    return import_module("app.api.endpoints.images").router


def _load_media_tasks() -> APIRouter:
    return import_module("app.api.endpoints.media_tasks").router


def _load_llm_chat() -> APIRouter:
    return import_module("app.api.endpoints.llm_chat").router


def _load_llm_stats() -> APIRouter:
    return import_module("app.api.endpoints.llm_stats").router


def _load_llm_manage() -> tuple[APIRouter, APIRouter]:
    module = import_module("app.api.endpoints.llm_manage")
    return module.router, module.legacy_router


def _load_tts() -> APIRouter:
    return import_module("app.api.endpoints.tts").router


def _load_ncm_login() -> APIRouter:
    return import_module("app.api.endpoints.ncm_login").router


def _load_persona_affect() -> APIRouter:
    return import_module("app.api.endpoints.persona_affect").router


ENDPOINT_LOADERS: dict[str, Callable[[], APIRouter | tuple[APIRouter, ...]]] = {
    "sing": _load_sing,
    "chat": _load_chat,
    "images": _load_images,
    "media_tasks": _load_media_tasks,
    "llm_chat": _load_llm_chat,
    "llm_stats": _load_llm_stats,
    "llm_manage": _load_llm_manage,
    "tts": _load_tts,
    "ncm_login": _load_ncm_login,
    "persona_affect": _load_persona_affect,
}


def build_api_router(enabled_endpoints: set[str] | frozenset[str]) -> APIRouter:
    router = APIRouter()
    for endpoint_name in enabled_endpoints:
        loader = ENDPOINT_LOADERS.get(endpoint_name)
        if loader is None:
            continue
        loaded = loader()
        if isinstance(loaded, tuple):
            for sub_router in loaded:
                router.include_router(sub_router)
            continue
        router.include_router(loaded)
    return router
