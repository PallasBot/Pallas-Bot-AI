import asyncio
import time
from typing import Any

from app.core.celery import celery_app
from app.core.config import settings
from app.core.llm_backend_runtime import (
    clear_llm_gpu_config_dirty,
    get_llm_num_gpu,
    is_llm_gpu_config_dirty,
    unload_resident_backend_model,
)
from app.core.logger import log_id_clause, log_id_suffix, logger
from app.providers.categorizer import classify_request_async, request_tier_for_metadata
from app.providers.chain import run_provider_chain
from app.providers.local_backend import unload_local_model
from app.providers.registry import load_provider_registry
from app.providers.router import infer_task, provider_configuration_error, resolve_model_name, resolve_provider_order
from app.providers.types import ChatCompletionParams, ProviderError
from app.services.callback import callback
from app.services.llm_messages import build_chat_messages, count_history_messages, is_pg_session
from app.services.llm_task_metrics import record_ai_llm_classification, record_ai_llm_task_from_metadata
from app.services.session_summary import maybe_compact_request_messages
from app.session import del_session, reset_session, save_messages

LLM_HISTORY_RESET_REPLY = "等等，刚才说到哪儿来着？我脑子里有点断片……"


@celery_app.task(name="llm_chat")
def llm_chat_task(
    request_id: str,
    session: str,
    text: str,
    system_prompt: str,
    model: str | None = None,
    chat_options: dict | None = None,
    metadata: dict | None = None,
    request_messages: list | None = None,
):
    meta = metadata if isinstance(metadata, dict) else {}
    logger.info(
        "LLM 任务入队：{}{}字数={}",
        log_id_clause(request_id),
        f"task={infer_task(meta)} ",
        len(text or ""),
    )
    started = time.monotonic()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            llm_chat_async(
                request_id,
                session,
                text,
                system_prompt,
                model,
                chat_options,
                metadata,
                request_messages,
            )
        )
    finally:
        logger.info(
            "LLM 任务完成：{}耗时={:.2f}s",
            log_id_clause(request_id),
            time.monotonic() - started,
        )
        loop.close()


async def llm_chat_async(
    request_id: str,
    session: str,
    text: str,
    system_prompt: str,
    model: str | None,
    chat_options: dict | None,
    metadata: dict | None,
    request_messages: list | None = None,
):
    meta = metadata if isinstance(metadata, dict) else {}
    succeeded = False
    try:
        if not settings.llm_chat_enabled:
            logger.warning("LLM 已关闭，跳过任务{}", log_id_suffix(request_id))
            await callback(request_id, status="failed")
            return

        config_error = provider_configuration_error()
        if config_error:
            logger.error("LLM 配置异常，跳过任务：{}{}", config_error, log_id_suffix(request_id))
            await callback(request_id, status="failed")
            return

        providers = resolve_provider_order(metadata=meta, user_text=text)
        if not providers:
            logger.error("LLM 无可用提供方，跳过任务{}", log_id_suffix(request_id))
            await callback(request_id, status="failed")
            return

        primary_provider = providers[0]
        primary_kind = load_provider_registry().kind_of(primary_provider)
        try:
            active_model = resolve_model_name(
                provider=primary_provider,
                metadata=meta,
                user_text=text,
                request_model=model,
            )
        except ValueError as exc:
            logger.error("LLM 模型解析失败{} err={}", log_id_suffix(request_id), exc)
            await callback(request_id, status="failed")
            return

        history_count = count_history_messages(meta, session, request_messages, text)
        session_mode = "pg" if is_pg_session(meta) and request_messages is not None else "redis"
        pending_summary: dict[str, Any] | None = None
        if session_mode == "pg" and request_messages is not None:
            request_messages, pending_summary = await maybe_compact_request_messages(
                request_messages,
                metadata=meta,
            )
            if pending_summary:
                history_count = count_history_messages(meta, session, request_messages, text)
        logger.info(
            "LLM 开始推理：{}提供方={} 模型={} 历史={}",
            log_id_clause(request_id),
            primary_provider,
            active_model,
            history_count,
        )

        max_messages = 2 * settings.llm_max_histories
        if history_count >= max_messages:
            if session_mode == "redis":
                reset_session(session, system_prompt)
                logger.warning("会话历史过长，已重置 session={}", session)
                await callback(request_id, text=LLM_HISTORY_RESET_REPLY)
                succeeded = True
                return
            if pending_summary is None:
                logger.warning("会话历史过长{} count={}", log_id_suffix(request_id), history_count)
                await callback(request_id, text=LLM_HISTORY_RESET_REPLY)
                succeeded = True
                return

        messages, session_mode = build_chat_messages(system_prompt, meta, session, text, request_messages)
        if session_mode == "redis":
            save_messages(session, messages)

        if settings.llm_tools_selective or settings.llm_categorizer_enabled or settings.llm_moe_enabled:
            task_name = infer_task(meta)
            classification = await classify_request_async(text, task=task_name, metadata=meta)
            meta = dict(meta)
            meta["classification"] = classification.to_dict()
            effective_tier = request_tier_for_metadata(text, meta)
            meta["classification"]["tier"] = effective_tier
            logger.info(
                "请求分类：{}tools={} tier={} vision={} source={}",
                log_id_clause(request_id),
                classification.needs_tools,
                effective_tier,
                classification.needs_vision,
                classification.source,
            )
            record_ai_llm_classification(meta)

        options: dict[str, float | int] = {}
        if isinstance(chat_options, dict):
            options.update({key: value for key, value in chat_options.items() if value is not None})
        if primary_kind == "local":
            num_gpu = get_llm_num_gpu()
            if num_gpu is not None:
                options["num_gpu"] = num_gpu
            if is_llm_gpu_config_dirty():
                logger.info(
                    "GPU 配置变更，卸载常驻模型{} model={} num_gpu={}",
                    log_id_suffix(request_id),
                    active_model,
                    num_gpu,
                )
                try:
                    await unload_local_model(active_model, provider_id=primary_provider)
                except Exception as exc:
                    logger.warning("GPU 卸载失败{} err={}", log_id_suffix(request_id), exc)

        params = ChatCompletionParams(
            request_id=request_id,
            session=session,
            user_text=text,
            system_prompt=system_prompt,
            model=model,
            options=options,
            metadata=meta,
        )

        max_attempts = settings.llm_max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                reply, assistant_message = await run_provider_chain(params, messages)
                if session_mode == "redis":
                    messages.append(assistant_message)
                    save_messages(session, messages)
                logger.info(
                    "LLM 回复成功：{}字数={} 尝试={}/{}",
                    log_id_clause(request_id),
                    len(reply),
                    attempt,
                    max_attempts,
                )
                if primary_kind == "local" and get_llm_num_gpu() is not None:
                    clear_llm_gpu_config_dirty()
                callback_kwargs: dict[str, Any] = {}
                if pending_summary:
                    callback_kwargs["history_summary"] = str(pending_summary.get("summary") or "")
                    callback_kwargs["history_keep_messages"] = int(pending_summary.get("keep_messages") or 0)
                await callback(request_id, text=reply, **callback_kwargs)
                succeeded = True
                return
            except ProviderError as exc:
                last_error = exc
                logger.error(
                    "LLM 提供方失败：{}provider={} status={} 尝试={}/{} err={}",
                    log_id_clause(request_id),
                    exc.provider,
                    exc.status,
                    attempt,
                    max_attempts,
                    exc,
                )
            except Exception as exc:
                last_error = exc
                logger.exception(
                    "LLM 未知异常{} 尝试={}/{}",
                    log_id_suffix(request_id),
                    attempt,
                    max_attempts,
                )
            if attempt < max_attempts:
                await asyncio.sleep(settings.llm_retry_backoff)

        logger.error("LLM 重试耗尽{} err={}", log_id_suffix(request_id), last_error)
        await callback(request_id, status="failed")
    finally:
        record_ai_llm_task_from_metadata(meta, "task_ok" if succeeded else "task_fail")


@celery_app.task(name="llm_del_session")
def llm_del_session_task(session: str) -> None:
    logger.info("已删除 LLM 会话 session={}", session)
    del_session(session)


async def unload_local_backend_model(model: str | None = None) -> tuple[int, str]:
    return await unload_resident_backend_model(model)
