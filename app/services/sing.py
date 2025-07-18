import random
from pathlib import Path

from app.core.config import settings
from app.core.logger import logger
from app.services.callback import callback_audio, callback_failed
from app.tasks.sing import sing_task

SONG_PATH = "resource/sing/splices/"
MUSIC_PATH = "resource/music/"


async def sing(request_id: str, speaker: str, song_id: int, sing_length: int, key: int, chunk_index: int):
    task = sing_task.delay(request_id, speaker, song_id, sing_length, chunk_index, key)
    logger.info(f"Task {task.id} started")
    return task.id


def get_random_song(speaker: str = ""):
    all_song = []
    if Path(SONG_PATH).exists():
        all_song = [
            str(s)
            for s in Path(SONG_PATH).iterdir()
            # 只唱过一段的大概率不是什么好听的，排除下
            if speaker in s.name and "_spliced0" not in s.name
        ]
    if not all_song:
        all_song = [MUSIC_PATH + s for s in Path(MUSIC_PATH).iterdir()]

    if not all_song:
        return None
    return random.choice(all_song)


async def play(speaker: str = ""):
    rand_music = get_random_song(speaker)
    if not rand_music:
        await callback_failed()
        return

    if "_spliced" in rand_music:
        splited = Path(rand_music).stem.split("_")
        song_id = splited[0]
        chunk_index = int(splited[1].replace("spliced", "")) + 1
    elif "_full_" in rand_music:
        song_id = Path(rand_music).stem.split("_")[0]
        chunk_index = 114514
    else:
        song_id = ""
        chunk_index = 114514

    await callback_audio(speaker, song_id, 0, chunk_index, rand_music)
