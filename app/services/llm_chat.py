from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.llm_backend_runtime import get_llm_num_gpu
from app.core.logger import log_id_clause, logger
from app.providers.router import infer_task, provider_configuration_error
from app.schemas.llm_chat import LlmChatCompletionRequest, LlmChatMode
from app.services.llm_messages import is_pg_session
from app.services.llm_queue import delete_chat_session, queue_llm_chat


def extract_user_text(request: LlmChatCompletionRequest) -> str:
    for item in reversed(request.messages):
        if str(item.role).strip().lower() == "user":
            return str(item.content or "").strip()
    return ""


def resolve_chat_temperature(mode: str) -> float:
    if LlmChatMode.normalize(mode) == LlmChatMode.DRUNK:
        return max(0.0, min(2.0, float(settings.llm_drunk_temperature)))
    return max(0.0, min(2.0, float(settings.llm_temperature)))


def resolve_chat_options(request: LlmChatCompletionRequest) -> dict[str, Any]:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    mode = LlmChatMode.normalize(str(metadata.get("mode") or LlmChatMode.NORMAL))
    raw_temperature = metadata.get("temperature")
    if isinstance(raw_temperature, int | float):
        temperature = max(0.0, min(2.0, float(raw_temperature)))
    else:
        temperature = resolve_chat_temperature(mode)
    options: dict[str, Any] = {"temperature": temperature}
    num_gpu = get_llm_num_gpu()
    if num_gpu is not None:
        options["num_gpu"] = num_gpu
    token_count = metadata.get("token_count")
    if isinstance(token_count, int | float) and int(token_count) > 0:
        options["num_predict"] = int(token_count)
    if metadata.get("think") is not None:
        options["think"] = bool(metadata.get("think"))
    return options


def build_submit_metadata(request: LlmChatCompletionRequest) -> dict[str, Any]:
    metadata = dict(request.metadata) if isinstance(request.metadata, dict) else {}
    metadata.setdefault("task", infer_task(metadata))
    metadata.setdefault("mode", str(metadata.get("mode") or LlmChatMode.NORMAL))
    return metadata


async def submit_llm_chat_completion(request_id: str, request: LlmChatCompletionRequest) -> str:
    if not settings.llm_chat_enabled:
        raise RuntimeError("llm chat backend disabled")

    config_error = provider_configuration_error()
    if config_error:
        raise RuntimeError(config_error)

    user_text = extract_user_text(request)
    if not user_text:
        raise ValueError("empty user message")

    metadata = build_submit_metadata(request)
    mode = LlmChatMode.normalize(str(metadata.get("mode") or LlmChatMode.NORMAL))
    logger.info(
        "LLM 请求入队：{}mode={} task={} 字数={}",
        log_id_clause(request_id),
        mode,
        metadata.get("task"),
        len(user_text),
    )
    request_messages: list[dict[str, str]] | None = None
    if is_pg_session(metadata):
        request_messages = [{"role": item.role, "content": item.content} for item in request.messages]

    return await queue_llm_chat(
        request_id,
        request.session_id,
        user_text,
        request.system,
        request.model,
        chat_options=resolve_chat_options(request),
        metadata=metadata,
        request_messages=request_messages,
    )


async def delete_llm_chat_session(session_id: str) -> None:
    await delete_chat_session(session_id)
