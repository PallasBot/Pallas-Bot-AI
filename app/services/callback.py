import httpx

from app.core.config import settings
from app.utils.retry import async_retry

CALLBACK_URL = f"http://{settings.callback_host}:{settings.callback_port}/callback"


@async_retry(max_attempts=settings.callback_max_retries, delay=3)
async def send_callback(url: str, data: dict, files: dict = None):
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=data, files=files, timeout=settings.callback_timeout)
        resp.raise_for_status()
        return resp.json()


async def callback_failed(request_id: str):
    callback_url = f"{CALLBACK_URL}/{request_id}"
    await send_callback(callback_url, {"status": "failed"})


async def callback_text(request_id: str, text: str):
    callback_url = f"{CALLBACK_URL}/{request_id}"
    await send_callback(callback_url, {"status": "success", "text": text})


async def callback_audio(request_id: str, audio: bytes):
    callback_url = f"{CALLBACK_URL}/{request_id}"
    await send_callback(
        callback_url,
        {"status": "success"},
        files={"file": audio},
    )


async def callback_audio_with_info(request_id: str, audio: bytes, song_id: str, chunk_index: int, key: int):
    callback_url = f"{CALLBACK_URL}/{request_id}"
    await send_callback(
        callback_url,
        {
            "status": "success",
            "song_id": song_id,
            "chunk_index": chunk_index,
            "key": key,
        },
        files={"file": audio},
    )
