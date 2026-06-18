from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.providers.config_store import export_providers_for_api, save_providers_document
from app.providers.router import llm_health_snapshot
from app.schemas.providers_api import ProvidersConfigResponse, ProvidersDocument

from .llm_manage import router


@router.get("/llm/providers", response_model=ProvidersConfigResponse)
async def get_providers_config() -> ProvidersConfigResponse:
    if not settings.llm_chat_enabled:
        raise HTTPException(status_code=503, detail="llm chat backend disabled")
    payload = export_providers_for_api()
    return ProvidersConfigResponse(**payload)


@router.put("/llm/providers")
async def put_providers_config(body: ProvidersDocument) -> dict[str, Any]:
    if not settings.llm_chat_enabled:
        raise HTTPException(status_code=503, detail="llm chat backend disabled")
    path = save_providers_document(body.model_dump())
    health = llm_health_snapshot()
    return {
        "providers_file": str(path),
        "provider_status": health.get("provider_status", []),
        "task_routing": health.get("task_routing", {}),
    }
