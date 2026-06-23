from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.core.logger import log_id_clause, logger
from app.services.llm_token_metrics import record_llm_token_usage
from app.services.vision_messages import enrich_local_messages_for_vision

from . import local_backend, remote_backend
from .registry import load_provider_registry
from .router import (
    infer_task,
    normalize_chain_failure,
    resolve_model_name,
    resolve_provider_order,
)
from .tool_loop import complete_with_tool_loop, tool_schemas_for_metadata
from .types import ChatCompletionParams, ProviderError


def record_ai_llm_provider_result(
    *,
    task: str | None,
    provider: str | None,
    model: str | None,
    succeeded: bool,
    latency_ms: int | None = None,
    failure_class: str | None = None,
) -> None:
    try:
        from app.services.llm_task_metrics import record_ai_llm_provider_result as _record  # noqa: PLC0415
    except ImportError:
        return
    _record(
        task=task,
        provider=provider,
        model=model,
        succeeded=succeeded,
        latency_ms=latency_ms,
        failure_class=failure_class,
    )


def record_ai_llm_route(task: str | None, route: str | None) -> None:
    try:
        from app.services.llm_task_metrics import record_ai_llm_route as _record  # noqa: PLC0415
    except ImportError:
        return
    _record(task, route)


def record_usage_from_message(
    metadata: dict[str, Any] | None,
    message: dict[str, Any] | None,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    if not isinstance(message, dict):
        return
    usage = message.get("_usage")
    if not isinstance(usage, dict):
        return
    meta = metadata if isinstance(metadata, dict) else {}
    record_llm_token_usage(
        task=infer_task(meta),
        provider=provider,
        model=model,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )


def route_name_for_provider(
    provider_id: str,
    *,
    used_tools: bool,
    agent_stage_plan: tuple[str, ...] = (),
) -> str:
    normalized = str(provider_id or "").strip().lower()
    if used_tools:
        if agent_stage_plan:
            return "agent_tool_loop"
        return "tool_loop"
    if normalized == "remote":
        return "plain_llm_chat_remote"
    if normalized == "local":
        return "plain_llm_chat"
    return f"plain_{normalized}"


async def run_provider_chain(
    params: ChatCompletionParams,
    messages: list[dict[str, str]],
) -> tuple[str, dict[str, str]]:
    provider_ids = resolve_provider_order(metadata=params.metadata, user_text=params.user_text)
    failure_mode = normalize_chain_failure(settings.llm_chain_on_failure)
    registry = load_provider_registry()
    tool_schemas = tool_schemas_for_metadata(params.metadata, user_text=params.user_text)
    agent_stage_plan = ()
    if isinstance(params.metadata, dict):
        raw_plan = params.metadata.get("agent_stage_plan")
        if isinstance(raw_plan, list):
            agent_stage_plan = tuple(str(item or "").strip().lower() for item in raw_plan if str(item or "").strip())
    if tool_schemas:
        logger.info(
            "已启用工具调用：{}数量={}",
            log_id_clause(params.request_id),
            len(tool_schemas),
        )

    last_error: Exception | None = None
    for index, provider_id in enumerate(provider_ids):
        model = resolve_model_name(
            provider=provider_id,
            metadata=params.metadata,
            user_text=params.user_text,
            request_model=params.model,
        )
        logger.info(
            "尝试 LLM 提供方：{}provider={} model={} {}/{}",
            log_id_clause(params.request_id),
            provider_id,
            model,
            index + 1,
            len(provider_ids),
        )
        started = time.perf_counter()
        try:
            active_provider_id = provider_id
            if tool_schemas:

                async def complete_once(
                    working_messages: list[dict[str, Any]],
                    *,
                    model: str,
                    options: dict[str, Any],
                    tools: list[dict[str, Any]] | None,
                    provider_name: str = active_provider_id,
                ) -> dict[str, Any]:
                    if registry.kind_of(provider_name) == "remote":
                        message_obj = await remote_backend.complete_remote_message(
                            working_messages,
                            model=model,
                            options=options,
                            tools=tools,
                            provider_id=provider_name,
                        )
                    else:
                        vision_messages = await enrich_local_messages_for_vision(
                            working_messages,
                            metadata=params.metadata,
                            user_text=params.user_text,
                            provider_id=provider_name,
                        )
                        message_obj = await local_backend.complete_local_message(
                            vision_messages,
                            model=model,
                            options=options,
                            tools=tools,
                            provider_id=provider_name,
                        )
                    record_usage_from_message(
                        params.metadata,
                        message_obj,
                        provider=provider_name,
                        model=model,
                    )
                    return message_obj

                meta = params.metadata if isinstance(params.metadata, dict) else {}
                reply, assistant_message = await complete_with_tool_loop(
                    complete_once=complete_once,
                    messages=messages,
                    tool_schemas=tool_schemas,
                    metadata=meta,
                    model=model,
                    options=params.options,
                    user_text=params.user_text,
                )
                record_ai_llm_route(
                    infer_task(meta),
                    route_name_for_provider(
                        active_provider_id,
                        used_tools=True,
                        agent_stage_plan=agent_stage_plan,
                    ),
                )
            elif registry.kind_of(provider_id) == "remote":
                message_obj = await remote_backend.complete_remote_message(
                    messages,
                    model=model,
                    options=params.options,
                    tools=None,
                    provider_id=provider_id,
                )
                record_usage_from_message(
                    params.metadata,
                    message_obj,
                    provider=provider_id,
                    model=model,
                )
                record_ai_llm_route(
                    infer_task(params.metadata if isinstance(params.metadata, dict) else {}),
                    route_name_for_provider(provider_id, used_tools=False),
                )
                reply = str(message_obj.get("content", "") or "").strip()
                assistant_message = {"role": "assistant", "content": reply}
            else:
                vision_messages = await enrich_local_messages_for_vision(
                    messages,
                    metadata=params.metadata,
                    user_text=params.user_text,
                    provider_id=provider_id,
                )
                message_obj = await local_backend.complete_local_message(
                    vision_messages,
                    model=model,
                    options=params.options,
                    tools=None,
                    provider_id=provider_id,
                )
                record_usage_from_message(
                    params.metadata,
                    message_obj,
                    provider=provider_id,
                    model=model,
                )
                record_ai_llm_route(
                    infer_task(params.metadata if isinstance(params.metadata, dict) else {}),
                    route_name_for_provider(provider_id, used_tools=False),
                )
                reply = str(message_obj.get("content", "") or "").strip()
                assistant_message = {"role": "assistant", "content": reply}
            latency_ms = int((time.perf_counter() - started) * 1000)
            record_ai_llm_provider_result(
                task=infer_task(params.metadata if isinstance(params.metadata, dict) else {}),
                provider=provider_id,
                model=model,
                succeeded=True,
                latency_ms=latency_ms,
            )
            return reply, assistant_message
        except (ProviderError, ValueError) as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            failure_class = "provider_error" if isinstance(exc, ProviderError) else "invalid_request"
            record_ai_llm_provider_result(
                task=infer_task(params.metadata if isinstance(params.metadata, dict) else {}),
                provider=provider_id,
                model=model,
                succeeded=False,
                latency_ms=latency_ms,
                failure_class=failure_class,
            )
            last_error = exc
            logger.warning(
                "LLM 提供方不可用，切换下一个：{}provider={} err={}",
                log_id_clause(params.request_id),
                provider_id,
                exc,
            )
            if failure_mode == "fail" or index >= len(provider_ids) - 1:
                break
            continue

    if last_error is not None:
        raise last_error
    raise ProviderError("chain", "no provider available")
