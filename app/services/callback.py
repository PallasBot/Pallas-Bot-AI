import httpx

from app.core.config import settings
from app.utils.retry import async_retry

CALLBACK_URL = f"http://{settings.callback_host}:{settings.callback_port}/callback"


@async_retry(max_attempts=settings.callback_max_retries, delay=3)
async def send_callback(url: str, json_payload: dict, files: dict = None):
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=json_payload, files=files, timeout=settings.callback_timeout)
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
