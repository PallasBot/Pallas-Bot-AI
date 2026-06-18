"""Bot 侧 LLM tool 执行客户端。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings
from app.core.logger import logger


def bot_tool_execute_url() -> str:
    return (
        f"http://{settings.callback_host}:{settings.callback_port}"
        "/pallas/api/internal/llm/tools/execute"
    )


async def execute_bot_tool(
    *,
    name: str,
    arguments: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "name": name,
        "arguments": arguments,
        "bot_id": metadata.get("bot_id"),
        "group_id": metadata.get("group_id"),
        "user_id": metadata.get("user_id"),
    }
    timeout = httpx.Timeout(settings.callback_timeout)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(bot_tool_execute_url(), json=payload)
    except Exception as exc:
        logger.warning("bot tool execute request failed: tool={} err={}", name, exc)
        return {"ok": False, "error": str(exc)}
    if response.status_code != 200:
        detail = response.text[:500]
        try:
            detail = response.json()
        except Exception:
            pass
        return {"ok": False, "error": f"bot status {response.status_code}", "detail": detail}
    data = response.json()
    return data if isinstance(data, dict) else {"ok": True, "result": data}


def tool_result_message(call_id: str, name: str, result: dict[str, Any]) -> dict[str, str]:
    content = json.dumps({"tool": name, "result": result}, ensure_ascii=False)
    return {"role": "tool", "tool_call_id": call_id, "content": content}
