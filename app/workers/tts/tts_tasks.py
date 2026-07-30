import asyncio

from app.core.celery import celery_app
from app.media.models import resolve_tts_request
from app.media.services.callback import callback
from app.media.services.translator import translate_for_tts
from app.utils.gpu_locker import get_gpu_locker
from app.workers.tts.GPT_SoVITS.interface import tts_handle

gpu_locker = get_gpu_locker()


def tts_req(text: str, media_type: str = "wav"):
    original_text = text
    print(f"初始文本：{original_text}")
    text_lang_override = None
    translated_text = translate_for_tts(text)
    if translated_text:
        text = translated_text
        text_lang_override = "ja"
        print(f"翻译结果: {text}")
    elif translated_text is None:
        print("翻译未启用或失败，使用原文")

    req = resolve_tts_request(text=text, media_type=media_type)
    if text_lang_override:
        req["text_lang"] = text_lang_override

    try:
        audio_data = tts_handle(req)
    except Exception as e:
        print(f"TTS处理出错: {e}")
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
    with gpu_locker.acquire(
        unload_llm=True,
        owner={"kind": "tts", "request_id": request_id, "media_type": media_type},
    ):
        req = resolve_tts_request(text=text, media_type=media_type)
        translated_text = translate_for_tts(text)
        if translated_text:
            req["text"] = translated_text
            req["text_lang"] = "ja"
        # 未开启或翻译失败：保留原文与配置 text_lang（通常为 zh）
        audio_data = tts_handle(req)
    if audio_data:
        await callback(request_id, audio=audio_data)
    else:
        await callback(request_id, status="failed")
