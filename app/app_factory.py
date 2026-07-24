from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.api.routers import build_api_router, resolve_enabled_endpoints
from app.core.logger import logger
from app.core.startup_report import emit_startup_summary, register_startup_fact

if TYPE_CHECKING:
    from collections.abc import Iterable

API_VERSION = "4.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    enabled_endpoints = set(app.state.enabled_endpoints)
    register_startup_fact("endpoints", ",".join(sorted(enabled_endpoints)) or "none")
    emit_startup_summary(api_version=API_VERSION, role="api")
    yield
    logger.info("AI 服务已关闭")


def create_app(*, enabled_endpoints: Iterable[str] | None = None) -> FastAPI:
    selected = resolve_enabled_endpoints(frozenset(enabled_endpoints) if enabled_endpoints is not None else None)
    app = FastAPI(lifespan=lifespan)
    app.state.enabled_endpoints = selected
    app.include_router(build_api_router(selected), prefix="/api")

    def health_check():
        payload = {"status": "ok", "api_version": API_VERSION}
        if "images" in selected:
            from app.image_runtime import image_runtime_status  # noqa: PLC0415 — 按端点懒加载

            payload["image"] = image_runtime_status().model_dump()
        if "media_tasks" in selected:
            from app.media_task_runtime import media_task_runtime_status  # noqa: PLC0415

            payload["media_tasks"] = media_task_runtime_status().model_dump()
        if "tts" in selected:
            from app.runtime_health import tts_runtime_snapshot  # noqa: PLC0415

            payload["tts"] = tts_runtime_snapshot()
        return payload

    app.add_api_route("/health", health_check, methods=["GET"])
    app.add_api_route("/api/health", health_check, methods=["GET"])

    return app
