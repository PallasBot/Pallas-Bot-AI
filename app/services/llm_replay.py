from __future__ import annotations

from typing import Any

from app.providers.chain import run_provider_chain
from app.providers.types import ChatCompletionParams
from app.schemas.llm_replay import LlmReplayRequest, LlmReplayResponse


def replay_user_text(messages: list[dict[str, str]]) -> str:
    for item in reversed(messages):
        if str(item.get("role") or "").strip().lower() == "user":
            return str(item.get("content") or "").strip()
    return ""


async def run_llm_replay(request: LlmReplayRequest) -> LlmReplayResponse:
    messages = [{"role": item.role, "content": item.content} for item in request.messages]
    user_text = replay_user_text(messages)
    if not user_text:
        msg = "replay requires at least one user message"
        raise ValueError(msg)

    metadata: dict[str, Any] = dict(request.metadata_subset or {})
    task = str(request.task or metadata.get("task") or "llm_chat").strip() or "llm_chat"
    metadata["task"] = task
    if request.agent_stage_plan:
        metadata["agent_stage_plan"] = [str(item).strip() for item in request.agent_stage_plan if str(item).strip()]
    if request.tool_catalog:
        metadata["tool_catalog"] = dict(request.tool_catalog)
        metadata["tools_enabled"] = bool(request.tool_catalog.get("tools") or [])
        metadata["tool_schema_count"] = len(request.tool_catalog.get("tools") or [])
    runtime_debug = metadata.get("runtime_debug") if isinstance(metadata.get("runtime_debug"), dict) else {}
    runtime_debug = dict(runtime_debug)
    runtime_debug["replay_enabled"] = True
    runtime_debug["replay_mode"] = str(request.mode or "mock_tools").strip() or "mock_tools"
    if request.request_snapshot_id:
        runtime_debug["request_snapshot_id"] = request.request_snapshot_id
    metadata["runtime_debug"] = runtime_debug

    params = ChatCompletionParams(
        request_id=request.request_id,
        session=request.request_snapshot_id or request.request_id,
        user_text=user_text,
        system_prompt=request.system_prompt,
        model=None,
        options={},
        metadata=metadata,
    )
    reply, assistant_message = await run_provider_chain(params, messages)
    trace = assistant_message.get("_agent_trace") if isinstance(assistant_message, dict) else None
    return LlmReplayResponse(
        request_id=request.request_id,
        request_snapshot_id=request.request_snapshot_id,
        mode=str(request.mode or "mock_tools"),
        task=task,
        reply=reply,
        trace=trace if isinstance(trace, dict) else None,
        assistant_message=assistant_message if isinstance(assistant_message, dict) else {},
    )
