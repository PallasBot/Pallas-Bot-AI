from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from app.http.deps.api_auth import require_api_bearer_token
from app.http.routers import build_api_router

if TYPE_CHECKING:
    from collections.abc import Iterable


def build_v1_router(enabled_endpoints: Iterable[str]) -> APIRouter:
    """对外推荐入口：Token 非空时全路由强制 Bearer（见 require_api_bearer_token）。"""
    router = APIRouter(dependencies=[Depends(require_api_bearer_token)])
    router.include_router(build_api_router(frozenset(enabled_endpoints)))
    return router
