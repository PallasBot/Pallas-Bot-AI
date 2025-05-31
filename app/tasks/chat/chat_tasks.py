import asyncio

from asyncer import asyncify

from app.core.celery import celery_app
from app.core.config import settings
from app.services.callback import chat_failed, chat_text_success, chat_tts_success
from app.utils.gpu_locker import GPULockManager

from .model import Chat

chat = Chat(settings.chat_strategy)
gpu_locker = GPULockManager(settings.sing_cuda_device)


@celery_app.task(name="chat")
def chat_task(session: str, text: str, token_count: int, tts: bool):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_chat_task_async(session, text, token_count, tts))
    finally:
        loop.close()


async def _chat_task_async(session: str, text: str, token_count: int, tts: bool):
    ans = await asyncify(chat.chat)(session, text)
    if tts:
        await chat_tts_success(ans, ans.path)
    elif ans:
        await chat_text_success(ans)
    else:
        await chat_failed()


def del_session(session):
    chat.del_session(session)
