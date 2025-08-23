import asyncio

from app.core.celery import celery_app
from app.core.config import settings
from app.services.callback import callback
from app.tasks.tts.tts_tasks import tts_req
from app.utils.gpu_locker import GPULockManager

from .model import Chat

gpu_locker = GPULockManager(0)


class ChatManager:
    _instance: Chat | None = None

    @classmethod
    def get_chat(cls) -> Chat:
        if cls._instance is None:
            cls._instance = Chat(settings.chat_strategy)
        return cls._instance

    @classmethod
    def del_session(cls, session: str):
        if cls._instance is not None:
            cls._instance.del_session(session)


@celery_app.task(name="chat")
def chat_task(request_id: str, session: str, text: str, token_count: int, tts: bool):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_chat_task_async(request_id, session, text, token_count, tts))
    finally:
        loop.close()


async def _chat_task_async(request_id: str, session: str, text: str, token_count: int, tts: bool):
    with gpu_locker.acquire():
        chat = ChatManager.get_chat()
        ans = chat.chat(session, text, token_count)
    if not ans:
        await callback(request_id, status="failed")
        return
    if tts:
        audio = tts_req(ans)
        if audio:
            await callback(request_id, text=ans, audio=audio)
            return
    await callback(request_id, text=ans)
