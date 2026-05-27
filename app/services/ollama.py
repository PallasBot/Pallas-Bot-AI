from app.core.logger import logger
from app.tasks.ollama import ollama_chat_task, ollama_del_session, ollama_unload


async def ollama_chat(
    request_id: str,
    session: str,
    text: str,
    system_prompt: str,
    model: str | None = None,
) -> str:
    task = ollama_chat_task.delay(request_id, session, text, system_prompt, model)
    logger.info(
        "ollama chat queued: request_id={} celery_task={} session={} text_len={} model={}",
        request_id,
        task.id,
        session,
        len(text or ""),
        (model or "").strip() or "(default)",
    )
    return task.id


async def del_session(session: str) -> None:
    logger.info("ollama del_session: {}", session)
    ollama_del_session(session)


async def unload(model: str | None = None) -> tuple[int, str]:
    return await ollama_unload(model)
