from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.core.logger import logger
from app.core.startup_report import emit_startup_summary, register_startup_fact
from app.http.routers import build_api_router, resolve_enabled_endpoints
from app.http.v1_router import build_v1_router
from app.version import VERSION

if TYPE_CHECKING:
    from collections.abc import Iterable

API_VERSION = VERSION


@asynccontextmanager
async def lifespan(app: FastAPI):
    enabled_endpoints = set(app.state.enabled_endpoints)
    register_startup_fact("endpoints", ",".join(sorted(enabled_endpoints)) or "none")
    emit_startup_summary(api_version=API_VERSION, role="api")
    yield
    logger.info("AI service stopped")


def create_app(*, enabled_endpoints: Iterable[str] | None = None) -> FastAPI:
    selected = resolve_enabled_endpoints(frozenset(enabled_endpoints) if enabled_endpoints is not None else None)
    app = FastAPI(
        lifespan=lifespan,
        title="Pallas Bot AI",
        description="媒体侧车 API。推荐使用 `/v1`（Bearer 鉴权）；`/api` 为兼容入口，后续废弃。",
        version=API_VERSION,
    )
    app.state.enabled_endpoints = selected
    app.include_router(build_api_router(selected), prefix="/api")
    app.include_router(build_v1_router(selected), prefix="/v1")

    def health_check():
        payload = {
            "status": "ok",
            "api_version": API_VERSION,
            "api": {
                "legacy_prefix": "/api",
                "recommended_prefix": "/v1",
                "deprecated_prefix": "/api",
            },
        }
        if "media_tasks" in selected:
            from app.media.runtime import media_task_runtime_status  # noqa: PLC0415

            payload["media_tasks"] = media_task_runtime_status().model_dump()
        if "tts" in selected:
            from app.media.health import tts_runtime_snapshot  # noqa: PLC0415

            payload["tts"] = tts_runtime_snapshot()
        return payload

    app.add_api_route("/health", health_check, methods=["GET"])
    app.add_api_route("/api/health", health_check, methods=["GET"])

    return app
