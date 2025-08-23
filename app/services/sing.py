from ulid import ULID

from app.core.config import settings
from app.core.logger import logger
from app.tasks.sing import play_task, request_task, sing_task


async def sing(request_id: str, speaker: str, song_id: int, key: int, chunk_index: int):
    task = sing_task.delay(request_id, speaker, song_id, settings.sing_length, chunk_index, key)
    logger.info(f"Task {task.id} started")
    return task.id


async def play(speaker: str = ""):
    request_id = str(ULID())
    task = play_task.delay(request_id, speaker)
    logger.info(f"Task {task.id} started")
    return request_id


async def download(request_id: str, song_id: int):
    task = request_task.delay(request_id, song_id)
    logger.info(f"Task {task.id} started")
    return task.id
