from fastapi import HTTPException

from app.core.celery import require_celery_task_package, resolve_celery_queue_for_task
from app.core.config import settings
from app.core.logger import logger


def ensure_sing_worker() -> None:
    try:
        require_celery_task_package("sing")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


async def sing(
    request_id: str,
    speaker: str,
    song_id: int,
    key: int,
    chunk_index: int,
    sing_length: int | None = None,
):
    from app.tasks.sing import sing_task

    ensure_sing_worker()
    length = sing_length if sing_length is not None and sing_length > 0 else settings.sing_length
    task = sing_task.apply_async(
        args=(request_id, speaker, song_id, length, chunk_index, key),
        queue=resolve_celery_queue_for_task("sing"),
    )
    logger.info(f"Task {task.id} started")
    return task.id


async def play(request_id: str, speaker: str = ""):
    from app.tasks.sing import play_task

    ensure_sing_worker()
    task = play_task.apply_async(
        args=(request_id, speaker),
        queue=resolve_celery_queue_for_task("play"),
    )
    logger.info(f"Task {task.id} started")
    return request_id


async def download(request_id: str, song_id: int):
    from app.tasks.sing import request_task

    ensure_sing_worker()
    task = request_task.apply_async(
        args=(request_id, song_id),
        queue=resolve_celery_queue_for_task("request"),
    )
    logger.info(f"Task {task.id} started")
    return task.id
