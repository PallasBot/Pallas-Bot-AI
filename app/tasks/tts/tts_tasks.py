import asyncio

from app.core.celery import celery_app
from app.services.callback import callback_audio, callback_failed
from app.tasks.tts.GPT_SoVITS.interface import tts_handle
from app.utils.gpu_locker import GPULockManager

gpu_locker = GPULockManager(0)


def tts_req(text: str, media_type: str = "wav"):
    req = {
        "text": text,
        "text_lang": "zh",
        "ref_audio_path": "resource/tts/ref_audio/进驻设施.wav",
        "prompt_text": "この角で家具を倒してしまわないよう、気をつけますね。",
        "prompt_lang": "ja",
        "media_type": media_type,
        "streaming_mode": False,
        "return_fragment": False,
    }

    try:
        audio_data = tts_handle(req)
    except Exception:
        return None
    return audio_data


@celery_app.task(name="tts")
def tts_task(request_id: str, text: str, media_type: str = "wav"):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_tts_task_async(request_id, text, media_type))
    finally:
        loop.close()


async def _tts_task_async(request_id: str, text: str, media_type: str = "wav"):
    with gpu_locker.acquire():
        audio_data = tts_handle(text, media_type)
    if audio_data:
        await callback_audio(request_id, audio_data)
    else:
        await callback_failed(request_id)
