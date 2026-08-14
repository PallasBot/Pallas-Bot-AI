from __future__ import annotations

import asyncio

import anyio

from app.core.celery import celery_app
from app.core.logger import log_id_suffix, logger, task_log
from app.media.services.callback import callback


def run_celery_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()


@celery_app.task(name="request")
def request_task(request_id: str, song_id: int):
    return run_celery_async(_request_task_async(request_id, song_id))


async def _request_task_async(request_id: str, song_id: int):
    from app.media.services.ncm_loader import download  # noqa: PLC0415 — fast worker 需保持轻量导入

    # 从网易云下载
    task_log("request task started{} song_id={}", log_id_suffix(request_id), song_id)
    origin = await download(song_id)
    if not origin:
        logger.error("request task download failed{} song_id={}", log_id_suffix(request_id), song_id)
        await callback(request_id, status="failed")
        return False

    # 直接回调回去

    async with await anyio.open_file(origin, "rb") as f:
        file = await f.read()
        task_log(
            "request task sending callback{} song_id={} path={} bytes={}",
            log_id_suffix(request_id),
            song_id,
            origin,
            len(file),
        )
        await callback(
            request_id,
            audio=file,
            song_id=str(song_id),
            chunk_index=0,
            key=0,
        )

    task_log("request task completed{} song_id={} path={}", log_id_suffix(request_id), song_id, origin)
    return True
