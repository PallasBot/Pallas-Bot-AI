from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.api.routers import DEFAULT_ENDPOINTS, build_api_router
from app.core.config import settings
from app.core.llm_backend_runtime import (
    ensure_local_backend_ready,
    get_llm_model,
    stop_local_backend_if_started,
)
from app.core.logger import logger
from app.core.ollama_gpu_guard import (
    ensure_ollama_gpu_ready_sync,
    start_ollama_gpu_guard_background,
    stop_ollama_gpu_guard_background,
)
from app.core.startup_report import emit_startup_summary, register_startup_fact, register_startup_warning
from app.image_runtime import image_runtime_status
from app.media_task_runtime import media_task_runtime_status
from app.providers import llm_health_snapshot, local_is_required
from app.providers.router import provider_configuration_error
from app.runtime_health import tts_runtime_snapshot
from app.services.llm_task_metrics import (
    start_background_flush,
    stop_background_flush,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

API_VERSION = "4.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    enabled_endpoints = set(app.state.enabled_endpoints)
    register_startup_fact("endpoints", ",".join(sorted(enabled_endpoints)) or "none")
    llm_endpoints = {"chat", "llm_chat", "llm_manage", "llm_stats"}
    if llm_endpoints.intersection(enabled_endpoints):
        register_startup_fact("llm", "on" if settings.llm_chat_enabled else "off")
        if settings.llm_chat_enabled:
            config_error = provider_configuration_error()
            if config_error:
                register_startup_warning("llm_config", config_error)
            register_startup_fact("llm_mode", str(settings.llm_provider_mode or "local_only"))
            if local_is_required():
                await ensure_local_backend_ready()
                await asyncio.to_thread(ensure_ollama_gpu_ready_sync)
                start_ollama_gpu_guard_background()
                register_startup_fact("llm_model", get_llm_model())
    emit_startup_summary(api_version=API_VERSION, role="api")
    start_background_flush()
    yield
    stop_ollama_gpu_guard_background()
    stop_background_flush()
    if settings.llm_auto_start:
        stop_local_backend_if_started()
    logger.info("AI 服务已关闭")


def create_app(*, enabled_endpoints: Iterable[str] | None = None) -> FastAPI:
    selected = frozenset(enabled_endpoints or DEFAULT_ENDPOINTS)
    app = FastAPI(lifespan=lifespan)
    app.state.enabled_endpoints = selected
    app.include_router(build_api_router(selected), prefix="/api")

    @app.get("/health")
    def health_check():
        payload = {"status": "ok", "api_version": API_VERSION}
        if {"chat", "llm_chat", "llm_manage", "llm_stats"}.intersection(selected):
            payload["llm"] = llm_health_snapshot()
        if "images" in selected:
            payload["image"] = image_runtime_status().model_dump()
        if "media_tasks" in selected:
            payload["media_tasks"] = media_task_runtime_status().model_dump()
        if "tts" in selected:
            payload["tts"] = tts_runtime_snapshot()
        return payload

    return app
