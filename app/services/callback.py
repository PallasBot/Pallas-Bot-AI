import httpx

from app.core.config import settings
from app.core.logger import logger
from app.utils.retry import async_retry

CALLBACK_URL = f"http://{settings.callback_host}:{settings.callback_port}/callback"


def should_retry_callback(exc: BaseException) -> bool:
    return not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code >= 500


@async_retry(
    max_attempts=settings.callback_max_retries,
    delay=3,
    retry_filter=should_retry_callback,
)
async def send_callback(url: str, data: dict, files: dict = None):
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=data, files=files, timeout=settings.callback_timeout)
        resp.raise_for_status()
        return resp.json()


async def callback(
    request_id: str,
    status: str = "success",
    text: str = None,
    audio: bytes = None,
    song_id: str = None,
    chunk_index: int = None,
    key: int = None,
):
    callback_url = f"{CALLBACK_URL}/{request_id}"

    data = {"status": status}

    if status == "failed":
        try:
            await send_callback(callback_url, data)
        except httpx.HTTPStatusError as err:
            logger.warning(
                "callback failed permanently: request_id={} status={} url={}",
                request_id,
                err.response.status_code,
                callback_url,
            )
        return

    if text:
        data["text"] = text
    if song_id:
        data["song_id"] = song_id
    if chunk_index is not None:
        data["chunk_index"] = chunk_index
    if key is not None:
        data["key"] = key

    try:
        if audio:
            await send_callback(callback_url, data, files={"file": audio})
        else:
            await send_callback(callback_url, data)
    except httpx.HTTPStatusError as err:
        logger.warning(
            "callback failed permanently: request_id={} status={} url={}",
            request_id,
            err.response.status_code,
            callback_url,
        )
