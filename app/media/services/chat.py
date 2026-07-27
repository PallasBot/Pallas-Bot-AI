from app.core.celery import require_celery_task_package, resolve_celery_queue_for_task
from app.core.logger import logger
from app.workers.chat import ChatManager, chat_task


async def chat(request_id: str, session: str, text: str, token_count: int, tts: bool):
    logger.info("legacy chat: request_id={} session={}", request_id, session)
    require_celery_task_package("chat")
    task = chat_task.apply_async(
        args=[request_id, session, text, token_count, tts],
        queue=resolve_celery_queue_for_task("chat"),
    )
    return task.id


async def del_session(session: str):
    ChatManager.del_session(session)
