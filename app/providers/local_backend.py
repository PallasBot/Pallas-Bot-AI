from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import settings
from app.core.logger import logger, task_log

from .registry import LlmProviderSpec, load_provider_registry, local_base_url_for_spec
from .token_usage import usage_from_local_chat_response
from .types import ChatCompletionParams, ProviderError


def resolve_local_provider(provider_id: str | None = None) -> tuple[str, LlmProviderSpec, str]:
    registry = load_provider_registry()
    pid = (provider_id or registry.legacy_local_id()).strip() or "local"
    spec = registry.get(pid)
    if spec is None or spec.kind != "local" or not spec.is_configured():
        pid = registry.legacy_local_id()
        spec = registry.get(pid)
    if spec is None or spec.kind != "local":
        raise ProviderError(pid, "local provider not found")
    base_url = local_base_url_for_spec(spec)
    if not base_url:
        raise ProviderError(pid, "local base url not configured")
    return pid, spec, base_url


def local_chat_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/chat"


def local_tags_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/tags"


def local_generate_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/api/generate"


def ping_local_provider_sync(provider_id: str, timeout: float = 2.0) -> bool:
    try:
        _, _, base_url = resolve_local_provider(provider_id)
    except ProviderError:
        return False
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            response = client.get(local_tags_url(base_url))
            return response.status_code == 200
    except httpx.HTTPError:
        return False


async def complete_local_message(
    messages: list[dict[str, Any]],
    *,
    model: str,
    options: dict[str, Any],
    tools: list[dict[str, Any]] | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    pid, _, base_url = resolve_local_provider(provider_id)
    payload_options: dict[str, float | int] = {}
    if isinstance(options, dict):
        for key, value in options.items():
            if value is None:
                continue
            if key == "num_predict":
                payload_options["num_predict"] = int(value)
            elif key == "temperature":
                payload_options["temperature"] = float(value)
            elif key == "num_gpu":
                payload_options["num_gpu"] = int(value)

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": payload_options,
    }
    think = options.get("think") if isinstance(options, dict) else None
    if think is None:
        think = settings.llm_think_enabled
    payload["think"] = bool(think)
    if tools:
        payload["tools"] = tools
    task_log(
        "local llm backend request: provider={} model={} num_gpu={}",
        pid,
        model,
        payload_options.get("num_gpu"),
    )
    timeout = httpx.Timeout(settings.llm_request_timeout)
    if settings.gpu_lock_llm_enabled:
        # 单卡：LLM 取读锁（彼此并发，仅与媒体写锁互斥），媒体上卡时自然让路。
        from app.utils.gpu_locker import acquire_gpu_read_async

        async with acquire_gpu_read_async():
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(local_chat_url(base_url), json=payload)
    else:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(local_chat_url(base_url), json=payload)
    if response.status_code != 200:
        logger.error(
            "local llm backend failed: provider={} status={} body={}",
            pid,
            response.status_code,
            response.text[:500],
        )
        raise ProviderError(pid, f"local backend status {response.status_code}", status=response.status_code)
    data = response.json()
    message_obj = data.get("message", {})
    if not isinstance(message_obj, dict):
        raise ProviderError(pid, "invalid local backend message")
    if not str(message_obj.get("content", "") or "").strip() and not message_obj.get("tool_calls"):
        raise ProviderError(pid, "empty local backend content")
    prompt_tokens, completion_tokens = usage_from_local_chat_response(data if isinstance(data, dict) else {})
    if prompt_tokens or completion_tokens:
        message_obj = dict(message_obj)
        message_obj["_usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
    return message_obj


async def complete_local(
    messages: list[dict[str, str]],
    *,
    model: str,
    options: dict[str, Any],
    provider_id: str | None = None,
) -> str:
    message_obj = await complete_local_message(
        messages,
        model=model,
        options=options,
        tools=None,
        provider_id=provider_id,
    )
    return str(message_obj.get("content", "") or "").strip()


async def complete_with_params(
    params: ChatCompletionParams,
    messages: list[dict[str, str]],
    model: str,
    *,
    provider_id: str | None = None,
) -> str:
    _ = params
    return await complete_local(
        messages,
        model=model,
        options=params.options,
        provider_id=provider_id,
    )


def unload_local_model_sync(
    model: str | None = None,
    *,
    provider_id: str | None = None,
) -> tuple[int, str]:
    pid, _, base_url = resolve_local_provider(provider_id)
    target = (model or "").strip()
    if not target:
        return 200, ""
    logger.info("llm backend unload sync: provider={} model={}", pid, target)
    payload = {
        "model": target,
        "keep_alive": 0,
    }
    timeout = httpx.Timeout(settings.llm_request_timeout)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(local_generate_url(base_url), json=payload)
        return response.status_code, response.text


async def unload_local_model(
    model: str | None = None,
    *,
    provider_id: str | None = None,
) -> tuple[int, str]:
    return await asyncio.to_thread(unload_local_model_sync, model, provider_id=provider_id)
