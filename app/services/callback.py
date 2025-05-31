import anyio
import httpx

from app.core.config import settings
from app.utils.retry import async_retry


@async_retry(max_attempts=settings.callback_max_retries, delay=3)
async def send_callback(url: str, json_payload: dict, files: dict = None):
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=json_payload, files=files, timeout=settings.callback_timeout)
        resp.raise_for_status()
        return resp.json()


async def sing_failed():
    callback_url = f"http://{settings.callback_host}:{settings.callback_port}/{settings.sing_callback_endpoint}"
    await send_callback(callback_url, {"status": "failed"})


async def sing_success(speaker: str, song_id: int, key: int, chunk_index: int, path: str):
    callback_url = f"http://{settings.callback_host}:{settings.callback_port}/{settings.sing_callback_endpoint}"
    async with await anyio.open_file(path, "rb") as f:
        file = await f.read()
        await send_callback(
            callback_url,
            {"status": "success", "speaker": speaker, "song_id": song_id, "key": key, "chunk_index": chunk_index},
            files={"file": file},
        )


async def chat_failed():
    callback_url = f"http://{settings.callback_host}:{settings.callback_port}/{settings.chat_callback_endpoint}"
    await send_callback(callback_url, {"status": "failed"})


async def chat_text_success(text: str):
    callback_url = f"http://{settings.callback_host}:{settings.callback_port}/{settings.chat_callback_endpoint}"
    await send_callback(
        callback_url,
        {"status": "success", "text": text},
    )


async def chat_tts_success(text: str, path: str):
    callback_url = f"http://{settings.callback_host}:{settings.callback_port}/{settings.chat_callback_endpoint}"
    async with await anyio.open_file(path, "rb") as f:
        file = await f.read()
        await send_callback(
            callback_url,
            {"status": "success", "text": text},
            files={"file": file},
        )
