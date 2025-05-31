from app.core.logger import logger
from app.tasks.chat import chat_task

SONG_PATH = "resource/sing/splices/"
MUSIC_PATH = "resource/music/"


async def chat(session: str, text: str, token_count: int, tts: bool):
    task = chat_task.delay(session, text, token_count, tts)
    logger.info(f"Task {task.id} started")
    return task.id
