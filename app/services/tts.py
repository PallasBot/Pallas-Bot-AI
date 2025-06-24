from app.core.logger import logger
from app.tasks.tts import tts_task


async def tts(request_id: str, text: str):
    task = tts_task.delay(request_id, text)
    logger.info(f"Task {task.id} started")
    return task.id
