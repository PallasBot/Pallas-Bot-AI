"""带 tool call 的多轮补全。"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.logger import logger
from app.providers.categorizer import needs_tools_for_request
from app.providers.operator_lookup import (
    extract_operator_lookup_name,
    operator_get_tool_registered,
)
from app.providers.tool_schema import canonical_tool_names, resolve_canonical_tool_name
from app.providers.tools import resolve_tool_schemas
from app.services.bot_tools import execute_bot_tool, tool_result_message

_OPERATOR_GET_TOOL = "arknights.operator.get"


def parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def prefetch_operator_tool(
    *,
    working: list[dict[str, Any]],
    user_text: str,
    metadata: dict[str, Any],
    registered_names: frozenset[str],
) -> bool:
    if not operator_get_tool_registered(registered_names):
        return False
    operator_name = extract_operator_lookup_name(user_text)
    if not operator_name:
        return False
    call_id = "prefetch_operator"
    logger.info("工具预取：tool={} name={}", _OPERATOR_GET_TOOL, operator_name)
    tool_result = await execute_bot_tool(
        name=_OPERATOR_GET_TOOL,
        arguments={"name": operator_name},
        metadata=metadata,
    )
    working.extend([
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": _OPERATOR_GET_TOOL,
                        "arguments": json.dumps({"name": operator_name}, ensure_ascii=False),
                    },
                }
            ],
        },
        tool_result_message(call_id, _OPERATOR_GET_TOOL, tool_result),
    ])
    return True


async def complete_with_tool_loop(
    *,
    complete_once,
    messages: list[dict[str, Any]],
    tool_schemas: list[dict[str, Any]],
    metadata: dict[str, Any],
    model: str,
    options: dict[str, Any],
    user_text: str = "",
) -> tuple[str, dict[str, str]]:
    """complete_once(messages, tools=..., model=..., options=...) -> message dict。"""
    if not tool_schemas:
        reply = await complete_once(messages, model=model, options=options, tools=None)
        return str(reply.get("content", "") or "").strip(), {"role": "assistant", "content": reply.get("content", "")}

    working = list(messages)
    if tool_schemas:
        meta = metadata if isinstance(metadata, dict) else {}
        task = str(meta.get("task") or "")
        if needs_tools_for_request(user_text, task=task, metadata=meta) or bool(meta.get("tools_enabled")):
            reminder = {
                "role": "system",
                "content": "涉及游戏角色、干员或敌人资料时，必须先调用已注册工具查询后再回答，不要凭记忆编造。",
            }
            insert_idx = 1 if working and working[0].get("role") == "system" else 0
            working.insert(insert_idx, reminder)

    max_rounds = max(1, int(settings.llm_tools_max_rounds))
    last_message: dict[str, Any] = {}
    registered_names = canonical_tool_names(tool_schemas)

    for round_idx in range(max_rounds):
        last_message = await complete_once(working, model=model, options=options, tools=tool_schemas)
        tool_calls = last_message.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            meta = metadata if isinstance(metadata, dict) else {}
            task = str(meta.get("task") or "")
            tools_needed = needs_tools_for_request(user_text, task=task, metadata=meta) or bool(
                meta.get("tools_enabled")
            )
            if round_idx == 0 and tools_needed:
                prefetched = await prefetch_operator_tool(
                    working=working,
                    user_text=user_text,
                    metadata=meta,
                    registered_names=registered_names,
                )
                if prefetched:
                    continue
            content = str(last_message.get("content", "") or "").strip()
            assistant_message = dict(last_message)
            assistant_message.setdefault("role", "assistant")
            assistant_message["content"] = content
            return content, assistant_message

        working.append({
            "role": "assistant",
            "content": last_message.get("content") or "",
            "tool_calls": tool_calls,
        })
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            fn = call.get("function") if isinstance(call.get("function"), dict) else {}
            tool_name = resolve_canonical_tool_name(
                str(fn.get("name") or call.get("name") or "").strip(),
                registered_names,
            )
            if not tool_name:
                continue
            call_id = str(call.get("id") or tool_name)
            args = parse_tool_arguments(fn.get("arguments"))
            logger.info(
                "工具调用：round={} tool={} 参数={}",
                round_idx + 1,
                tool_name,
                sorted(args.keys()),
            )
            tool_result = await execute_bot_tool(name=tool_name, arguments=args, metadata=metadata)
            working.append(tool_result_message(call_id, tool_name, tool_result))

    content = str(last_message.get("content", "") or "").strip()
    if not content:
        content = "抱歉，工具调用次数已达上限，请换个说法再试。"
    return content, {"role": "assistant", "content": content}


def tool_schemas_for_metadata(
    metadata: dict[str, Any] | None,
    *,
    user_text: str = "",
) -> list[dict[str, Any]]:
    meta = metadata if isinstance(metadata, dict) else {}
    return resolve_tool_schemas(
        task=str(meta.get("task") or ""),
        metadata=meta,
        user_text=user_text,
    )
