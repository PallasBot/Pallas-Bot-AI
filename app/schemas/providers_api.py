from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ProviderRow(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="remote")
    base_url: str = ""
    api_key_env: str = ""
    default_model: str = ""
    enabled: bool = True
    task_models: dict[str, str] = Field(default_factory=dict)


class ProviderRouting(BaseModel):
    chain_fallback: list[str] = Field(default_factory=list)
    tasks: dict[str, str] = Field(default_factory=dict)


class ProvidersDocument(BaseModel):
    providers: list[ProviderRow] = Field(default_factory=list)
    routing: ProviderRouting = Field(default_factory=ProviderRouting)


class ProvidersConfigResponse(BaseModel):
    providers: list[dict[str, Any]]
    routing: dict[str, Any]
    providers_file: str
    file_exists: bool


class ProviderModelsResponse(BaseModel):
    provider_id: str
    ok: bool
    models: list[str] = Field(default_factory=list)
    source: str = ""
    error: str = ""


class ProviderTestResponse(BaseModel):
    provider_id: str
    reachable: bool
    latency_ms: float | None = None
    error: str = ""
