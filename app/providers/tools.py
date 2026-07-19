from __future__ import annotations

from typing import Any

from app.core.config import settings

from .categorizer import needs_tools_for_request


def schemas_from_tool_catalog(meta: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = meta.get("tool_catalog")
    if not isinstance(catalog, dict):
        return []
    tools = catalog.get("tools")
    if not isinstance(tools, list) or not tools:
        return []
    schemas: list[dict[str, Any]] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": str(item.get("description") or "").strip(),
                "parameters": item.get("parameters") or {"type": "object", "properties": {}},
            },
        })
    return schemas


def resolve_tool_schemas(
    *,
    task: str,
    metadata: dict[str, Any] | None = None,
    user_text: str = "",
) -> list[dict[str, Any]]:
    if not settings.llm_tools_enabled:
        return []
    meta = metadata if isinstance(metadata, dict) else {}
    if not meta.get("tools_enabled"):
        return []
    schemas = schemas_from_tool_catalog(meta)
    if not schemas:
        raw = meta.get("tool_schemas")
        if not isinstance(raw, list):
            _ = task
            return []
        schemas = [item for item in raw if isinstance(item, dict)]
    if not schemas:
        return []
    if settings.llm_tools_selective and not needs_tools_for_request(
        user_text,
        task=task,
        metadata=meta,
    ):
        return []
    return schemas
