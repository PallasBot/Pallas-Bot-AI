from app.core.logger import logger
from app.tasks.chat import ChatManager, chat_task


async def chat(request_id: str, session: str, text: str, token_count: int, tts: bool):
    task = chat_task.delay(request_id, session, text, token_count, tts)
    logger.info(f"Task {task.id} started")
    return task.id


async def del_session(session: str):
    ChatManager.del_session(session)
