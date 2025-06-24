import asyncio

from app.core.celery import celery_app
from app.core.config import settings
from app.services.callback import callback_audio, callback_failed, callback_text
from app.tasks.tts.tts_tasks import tts_req
from app.utils.gpu_locker import GPULockManager

from .model import Chat

chat = Chat(settings.chat_strategy)
gpu_locker = GPULockManager(0)


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
        ans = chat.chat(session, text, token_count)
    if not ans:
        await callback_failed(request_id)
        return
    print(f"Chat response: {ans}")
    if tts:
        audio = tts_req(ans)
        if audio:
            await callback_audio(request_id, audio)
            return
    await callback_text(session, ans)


def del_session(session):
    chat.del_session(session)
