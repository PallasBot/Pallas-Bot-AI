from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import settings
from app.providers.config_store import export_providers_for_api, save_providers_document
from app.providers.local_backend import local_tags_url, resolve_local_provider
from app.providers.registry import provider_spec_or_error
from app.providers.remote_backend import (
    ping_remote_provider_sync,
    remote_models_url_for_spec,
)
from app.providers.local_backend import ping_local_provider_sync
from app.providers.router import llm_health_snapshot
from app.providers.types import ProviderError
from app.schemas.providers_api import (
    ProviderModelsResponse,
    ProviderTestResponse,
    ProvidersConfigResponse,
    ProvidersDocument,
)

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


def _parse_ollama_tags(payload: Any) -> list[str]:
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return []
    out: list[str] = []
    for item in models:
        name = item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str) and name.strip():
            out.append(name.strip())
    return out


def _parse_openai_models(payload: Any) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        mid = item.get("id") if isinstance(item, dict) else None
        if isinstance(mid, str) and mid.strip():
            out.append(mid.strip())
    return out


@router.get("/llm/providers/{provider_id}/models", response_model=ProviderModelsResponse)
async def list_provider_models(provider_id: str) -> ProviderModelsResponse:
    """在线发现某 Provider 的可用模型：local 走 /api/tags，remote 走 /v1/models。"""
    if not settings.llm_chat_enabled:
        raise HTTPException(status_code=503, detail="llm chat backend disabled")
    try:
        spec = provider_spec_or_error(provider_id)
    except ValueError as exc:
        return ProviderModelsResponse(provider_id=provider_id, ok=False, error=str(exc))

    try:
        if spec.kind == "local":
            _, _, base_url = resolve_local_provider(provider_id)
            url = local_tags_url(base_url)
            headers: dict[str, str] = {}
            parse = _parse_ollama_tags
            source = "ollama"
        else:
            url = remote_models_url_for_spec(spec)
            headers = {"Authorization": f"Bearer {spec.api_key}"} if spec.api_key else {}
            parse = _parse_openai_models
            source = "openai"
    except ProviderError as exc:
        return ProviderModelsResponse(provider_id=provider_id, ok=False, error=str(exc))

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        return ProviderModelsResponse(provider_id=provider_id, ok=False, source=source, error=str(exc))
    if response.status_code != 200:
        return ProviderModelsResponse(
            provider_id=provider_id,
            ok=False,
            source=source,
            error=f"HTTP {response.status_code}",
        )
    try:
        payload = response.json()
    except ValueError:
        return ProviderModelsResponse(
            provider_id=provider_id, ok=False, source=source, error="invalid response"
        )
    return ProviderModelsResponse(
        provider_id=provider_id, ok=True, source=source, models=parse(payload)
    )


@router.post("/llm/providers/{provider_id}/test", response_model=ProviderTestResponse)
async def test_provider(provider_id: str) -> ProviderTestResponse:
    """实时连通性测试，复用已有 ping helper。"""
    if not settings.llm_chat_enabled:
        raise HTTPException(status_code=503, detail="llm chat backend disabled")
    try:
        spec = provider_spec_or_error(provider_id)
    except ValueError as exc:
        return ProviderTestResponse(provider_id=provider_id, reachable=False, error=str(exc))

    started = time.monotonic()
    if spec.kind == "local":
        reachable = await asyncio.to_thread(ping_local_provider_sync, provider_id)
    else:
        reachable = await asyncio.to_thread(ping_remote_provider_sync, provider_id)
    latency_ms = round((time.monotonic() - started) * 1000.0, 1)
    return ProviderTestResponse(
        provider_id=provider_id,
        reachable=bool(reachable),
        latency_ms=latency_ms,
        error="" if reachable else "provider unreachable",
    )
