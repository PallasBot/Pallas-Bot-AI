from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter

from app.http.routers import build_api_router

if TYPE_CHECKING:
    from collections.abc import Iterable


def build_v1_router(enabled_endpoints: Iterable[str]) -> APIRouter:
    """对外推荐入口；与兼容 /api 共用同一鉴权路由。"""
    router = APIRouter()
    router.include_router(build_api_router(frozenset(enabled_endpoints)))
    return router
