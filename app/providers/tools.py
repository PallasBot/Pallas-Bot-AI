from __future__ import annotations

from typing import Any

from app.core.config import settings

from .categorizer import needs_tools_for_request


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
