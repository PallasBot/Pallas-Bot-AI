from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.api.routers import DEFAULT_ENDPOINTS, build_api_router
from app.core.config import settings
from app.core.llm_backend_runtime import (
    ensure_local_backend_ready,
    stop_local_backend_if_started,
)
from app.core.logger import logger
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
    logger.info("AI 服务启动中…")
    if {"chat", "llm_chat", "llm_manage", "llm_stats"}.intersection(enabled_endpoints):
        if settings.llm_chat_enabled:
            config_error = provider_configuration_error()
            if config_error:
                logger.warning("LLM 提供方配置不完整：{}", config_error)
            if local_is_required():
                await ensure_local_backend_ready()
    logger.info("AI 服务已就绪，健康检查 GET /health")
    start_background_flush()
    yield
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
