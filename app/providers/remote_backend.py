from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings, settings
from app.core.logger import logger

from app.providers.registry import LlmProviderSpec, load_provider_registry, provider_spec_or_error
from app.providers.tool_schema import sanitize_tool_schemas_for_api
from .token_usage import usage_from_remote_chat_response
from .types import ProviderError


def remote_chat_completions_url_for_spec(spec: LlmProviderSpec) -> str:
    base = (spec.base_url or "").strip().rstrip("/")
    if not base:
        raise ProviderError(spec.id, "remote base url not configured")
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def remote_chat_completions_url(cfg: Settings | None = None) -> str:
    registry = load_provider_registry(cfg)
    spec = registry.get(registry.legacy_remote_id())
    if spec is None:
        raise ProviderError("remote", "remote base url not configured")
    return remote_chat_completions_url_for_spec(spec)


async def complete_remote_message(
    messages: list[dict[str, Any]],
    *,
    model: str,
    options: dict[str, Any],
    tools: list[dict[str, Any]] | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    registry = load_provider_registry()
    pid = (provider_id or registry.legacy_remote_id()).strip() or "remote"
    spec = provider_spec_or_error(pid)
    return await complete_remote_message_for_spec(
        messages,
        spec=spec,
        model=model,
        options=options,
        tools=tools,
    )


async def complete_remote_message_for_spec(
    messages: list[dict[str, Any]],
    *,
    spec: LlmProviderSpec,
    model: str,
    options: dict[str, Any],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not spec.api_key.strip():
        raise ProviderError(spec.id, "remote api key not configured")

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    temperature = options.get("temperature") if isinstance(options, dict) else None
    if isinstance(temperature, int | float):
        payload["temperature"] = float(temperature)
    token_count = options.get("num_predict") if isinstance(options, dict) else None
    if isinstance(token_count, int | float) and int(token_count) > 0:
        payload["max_tokens"] = int(token_count)
    if tools:
        payload["tools"] = sanitize_tool_schemas_for_api(tools)
        payload["tool_choice"] = "auto"
    if str(model).startswith("deepseek-v4"):
        payload["thinking"] = {"type": "disabled"}

    headers = {"Authorization": f"Bearer {spec.api_key}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(settings.llm_request_timeout)
    url = remote_chat_completions_url_for_spec(spec)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        logger.error(
            "remote llm backend failed: provider={} status={} body={}",
            spec.id,
            response.status_code,
            response.text[:500],
        )
        raise ProviderError(
            spec.id,
            f"remote backend status {response.status_code}",
            status=response.status_code,
        )

    data = response.json()
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError(spec.id, "empty remote choices")
    message_obj = choices[0].get("message") if isinstance(choices[0], dict) else {}
    if not isinstance(message_obj, dict):
        raise ProviderError(spec.id, "invalid remote message")
    if not str(message_obj.get("content", "") or "").strip() and not message_obj.get("tool_calls"):
        raise ProviderError(spec.id, "empty remote content")
    prompt_tokens, completion_tokens = usage_from_remote_chat_response(data if isinstance(data, dict) else {})
    if prompt_tokens or completion_tokens:
        message_obj = dict(message_obj)
        message_obj["_usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
    return message_obj


async def complete_remote(
    messages: list[dict[str, str]],
    *,
    model: str,
    options: dict[str, Any],
    provider_id: str | None = None,
) -> str:
    message_obj = await complete_remote_message(
        messages,
        model=model,
        options=options,
        tools=None,
        provider_id=provider_id,
    )
    return str(message_obj.get("content", "") or "").strip()


async def complete_with_params(
    params,
    messages: list[dict[str, str]],
    model: str,
    *,
    provider_id: str | None = None,
) -> str:
    _ = params
    return await complete_remote(messages, model=model, options=params.options, provider_id=provider_id)


def remote_models_url_for_spec(spec: LlmProviderSpec) -> str:
    base = (spec.base_url or "").strip().rstrip("/")
    if not base:
        raise ProviderError(spec.id, "remote base url not configured")
    if base.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def remote_models_url(cfg: Settings | None = None) -> str:
    registry = load_provider_registry(cfg)
    spec = registry.get(registry.legacy_remote_id())
    if spec is None:
        raise ProviderError("remote", "remote base url not configured")
    return remote_models_url_for_spec(spec)


def ping_remote_provider_sync(provider_id: str, timeout: float = 3.0, cfg: Settings | None = None) -> bool:
    try:
        spec = provider_spec_or_error(provider_id, cfg)
    except ValueError:
        return False
    if spec.kind != "remote":
        return False
    headers = {"Authorization": f"Bearer {spec.api_key}"}
    try:
        url = remote_models_url_for_spec(spec)
    except ProviderError:
        return False
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            response = client.get(url, headers=headers)
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def ping_remote_backend_sync(timeout: float = 3.0, cfg: Settings | None = None) -> bool:
    registry = load_provider_registry(cfg)
    return ping_remote_provider_sync(registry.legacy_remote_id(), timeout=timeout, cfg=cfg)
