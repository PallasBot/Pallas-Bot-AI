from app.core.logger import log_id_clause, logger, short_log_id
from app.providers.router import infer_task
from app.services.llm_task_metrics import record_ai_llm_task_state
from app.tasks.llm import llm_chat_task, llm_del_session_task, unload_local_backend_model


async def queue_llm_chat(
    request_id: str,
    session: str,
    text: str,
    system_prompt: str,
    model: str | None = None,
    *,
    chat_options: dict | None = None,
    metadata: dict | None = None,
    request_messages: list[dict[str, str]] | None = None,
) -> str:
    task = llm_chat_task.delay(
        request_id,
        session,
        text,
        system_prompt,
        model,
        chat_options,
        metadata,
        request_messages,
    )
    record_ai_llm_task_state(str(task.id), infer_task(metadata if isinstance(metadata, dict) else {}), "queued")
    celery_id = short_log_id(task.id)
    celery_part = f"celery={celery_id} " if celery_id else ""
    logger.info(
        "LLM 已提交 Celery：{}{}模型={}",
        log_id_clause(request_id),
        celery_part,
        (model or "").strip() or "(默认)",
    )
    return task.id


async def delete_chat_session(session: str) -> None:
    logger.info("已排队删除 LLM 会话 session={}", session)
    llm_del_session_task.delay(session)


async def unload_local_model(model: str | None = None) -> tuple[int, str]:
    return await unload_local_backend_model(model)
