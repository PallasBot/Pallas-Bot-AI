import asyncio
from typing import TYPE_CHECKING

from app.core.celery import celery_app
from app.core.config import settings
from app.core.logger import logger
from app.services.callback import callback
from app.tasks.tts.tts_tasks import tts_req
from app.utils.gpu_locker import get_gpu_locker

if TYPE_CHECKING:
    from .model import Chat

gpu_locker = get_gpu_locker()


def chat_uses_gpu() -> bool:
    strategy = str(settings.chat_strategy or "").strip().lower()
    return "cuda" in strategy


class ChatManager:
    _instance: "Chat | None" = None

    @classmethod
    def get_chat(cls) -> "Chat":
        if cls._instance is None:
            from .model import Chat

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
    try:
        if chat_uses_gpu():
            with gpu_locker.acquire(
                unload_llm=True,
                owner={"kind": "chat", "request_id": request_id, "session": session},
            ):
                chat = ChatManager.get_chat()
                ans = chat.chat(session, text, token_count)
        else:
            chat = ChatManager.get_chat()
            ans = chat.chat(session, text, token_count)
    except Exception:
        logger.exception("旧版 chat 任务初始化或执行失败：request_id={}", request_id)
        await callback(request_id, status="failed")
        return
    if not ans:
        await callback(request_id, status="failed")
        return
    if tts:
        audio = tts_req(ans)
        if audio:
            await callback(request_id, text=ans, audio=audio)
            return
    await callback(request_id, text=ans)
