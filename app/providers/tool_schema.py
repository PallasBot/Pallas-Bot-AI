"""OpenAI 兼容 API 的 tool schema 名称适配（DeepSeek 等禁止 function.name 含 `.`）。"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

_OPENAI_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def openai_api_tool_name(canonical: str) -> str:
    """将内部 tool 名映射为 OpenAI/DeepSeek 允许的 function.name。"""
    raw = (canonical or "").strip()
    if not raw:
        return "tool"
    if _OPENAI_TOOL_NAME_RE.fullmatch(raw):
        return raw
    out: list[str] = []
    for ch in raw:
        if ch.isalnum() or ch in "_-":
            out.append(ch)
        else:
            out.append("_")
    name = "".join(out).strip("_")
    return name or "tool"


def sanitize_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    item = copy.deepcopy(schema)
    fn = item.get("function")
    if not isinstance(fn, dict):
        return item
    canonical = str(fn.get("name") or "").strip()
    if canonical:
        fn["name"] = openai_api_tool_name(canonical)
    return item


def sanitize_tool_schemas_for_api(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [sanitize_tool_schema(item) for item in schemas if isinstance(item, dict)]


def sanitize_messages_for_api(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        item = copy.deepcopy(message)
        tool_calls = item.get("tool_calls")
        if isinstance(tool_calls, list):
            cleaned_calls: list[dict[str, Any]] = []
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                cleaned = copy.deepcopy(call)
                fn = cleaned.get("function")
                if isinstance(fn, dict):
                    canonical = str(fn.get("name") or "").strip()
                    if canonical:
                        fn["name"] = openai_api_tool_name(canonical)
                    arguments = fn.get("arguments")
                    if isinstance(arguments, dict | list):
                        fn["arguments"] = json.dumps(arguments, ensure_ascii=False)
                cleaned_calls.append(cleaned)
            item["tool_calls"] = cleaned_calls
        sanitized.append(item)
    return sanitized


def canonical_tool_names(schemas: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in schemas:
        if not isinstance(item, dict):
            continue
        fn = item.get("function")
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "").strip()
        if name:
            names.add(name)
    return names


def resolve_canonical_tool_name(api_name: str, canonical_names: set[str]) -> str:
    """把远端返回的 function.name 还原为 Bot 侧注册名。"""
    raw = (api_name or "").strip()
    if not raw:
        return raw
    if raw in canonical_names:
        return raw
    for canonical in canonical_names:
        if openai_api_tool_name(canonical) == raw:
            return canonical
    return raw
