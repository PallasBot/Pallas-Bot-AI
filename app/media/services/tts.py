from app.core.logger import log_id_clause, logger, short_log_id
from app.workers.tts import tts_task


async def tts(request_id: str, text: str):
    task = tts_task.delay(request_id, text)
    logger.info(
        "tts task submitted{} task={}",
        log_id_clause(request_id, label="request_id"),
        short_log_id(task.id),
    )
    return task.id
