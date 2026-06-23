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
_PLANNER_REMINDER = "先用一句话明确你的回答计划；若需要外部事实或插件能力，再调用工具，不要直接凭空编造。"


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


def resolve_agent_stage_plan(metadata: dict[str, Any] | None) -> tuple[str, ...]:
    meta = metadata if isinstance(metadata, dict) else {}
    raw = meta.get("agent_stage_plan")
    if not isinstance(raw, list):
        return ()
    stages: list[str] = []
    for item in raw:
        text = str(item or "").strip().lower()
        if text:
            stages.append(text)
    return tuple(stages)


def agent_stage_enabled(metadata: dict[str, Any] | None, stage: str) -> bool:
    plan = resolve_agent_stage_plan(metadata)
    if not plan:
        return True
    return str(stage or "").strip().lower() in plan


def build_agent_trace(
    *,
    metadata: dict[str, Any] | None,
    tool_schemas: list[dict[str, Any]],
) -> dict[str, Any]:
    plan = resolve_agent_stage_plan(metadata)
    return {
        "agent_stage_plan": list(plan),
        "planner_enabled": agent_stage_enabled(metadata, "plan"),
        "tool_loop_enabled": agent_stage_enabled(metadata, "tool_loop"),
        "tool_schema_count": len(tool_schemas),
        "tool_call_count": 0,
        "rounds": [],
        "prefetched_tool": None,
        "final_stage": "generate",
    }


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
    trace = build_agent_trace(metadata=metadata, tool_schemas=tool_schemas)
    if tool_schemas:
        meta = metadata if isinstance(metadata, dict) else {}
        if agent_stage_enabled(meta, "plan"):
            reminder = {"role": "system", "content": _PLANNER_REMINDER}
            insert_idx = 1 if working and working[0].get("role") == "system" else 0
            working.insert(insert_idx, reminder)
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
        round_trace = {
            "round": round_idx + 1,
            "tool_calls": [],
            "used_prefetch": False,
        }
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
                    round_trace["used_prefetch"] = True
                    trace["prefetched_tool"] = _OPERATOR_GET_TOOL
                    trace["rounds"].append(round_trace)
                    continue
            content = str(last_message.get("content", "") or "").strip()
            assistant_message = dict(last_message)
            assistant_message.setdefault("role", "assistant")
            assistant_message["content"] = content
            trace["rounds"].append(round_trace)
            assistant_message["_agent_trace"] = trace
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
            round_trace["tool_calls"].append(tool_name)
            trace["tool_call_count"] = int(trace.get("tool_call_count") or 0) + 1
            logger.info(
                "工具调用：round={} tool={} 参数={}",
                round_idx + 1,
                tool_name,
                sorted(args.keys()),
            )
            tool_result = await execute_bot_tool(name=tool_name, arguments=args, metadata=metadata)
            working.append(tool_result_message(call_id, tool_name, tool_result))
        trace["rounds"].append(round_trace)

    content = str(last_message.get("content", "") or "").strip()
    if not content:
        content = "抱歉，工具调用次数已达上限，请换个说法再试。"
    return content, {"role": "assistant", "content": content, "_agent_trace": trace}


def tool_schemas_for_metadata(
    metadata: dict[str, Any] | None,
    *,
    user_text: str = "",
) -> list[dict[str, Any]]:
    meta = metadata if isinstance(metadata, dict) else {}
    if not agent_stage_enabled(meta, "tool_loop"):
        return []
    return resolve_tool_schemas(
        task=str(meta.get("task") or ""),
        metadata=meta,
        user_text=user_text,
    )
