import asyncio
import random
from pathlib import Path

import anyio

from app.core.celery import celery_app
from app.services.callback import callback

SONG_PATH = "resource/sing/splices/"
MUSIC_PATH = "resource/music/"


def get_random_song(speaker: str = ""):
    all_song = []
    song_dir = Path(SONG_PATH)
    if song_dir.exists():
        all_song = [str(s) for s in song_dir.iterdir() if speaker in s.name and "_spliced0" not in s.name]

    if not all_song:
        music_dir = Path(MUSIC_PATH)
        if music_dir.exists():
            all_song = [str(s) for s in music_dir.iterdir()]

    if not all_song:
        return None
    return random.choice(all_song)


@celery_app.task(name="play")
def play_task(request_id: str, speaker: str = ""):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_play_task_async(request_id, speaker))
    finally:
        loop.close()


async def _play_task_async(request_id: str, speaker: str = ""):
    try:
        rand_music = get_random_song(speaker)
        if not rand_music:
            await callback(request_id, status="failed")
            return False

        if "_spliced" in rand_music:
            splited = Path(rand_music).stem.split("_")
            song_id = splited[0]
            chunk_index = int(splited[1].replace("spliced", "")) + 1
            if "key" in rand_music:
                key_index = next((i for i, part in enumerate(splited) if "key" in part), None)
                if key_index is not None:
                    try:
                        key = int(splited[key_index].replace("key", ""))
                    except ValueError:
                        key = 0
                else:
                    key = 0
            else:
                key = 0
        elif "_full_" in rand_music:
            song_id = Path(rand_music).stem.split("_")[0]
            chunk_index = 114514
            key = 0
        else:
            song_id = ""
            chunk_index = 114514
            key = 0

        try:
            async with await anyio.open_file(rand_music, "rb") as f:
                audio_content = await f.read()
        except Exception:
            await callback(request_id, status="failed")
            return False

        await callback(request_id, audio=audio_content, song_id=song_id, chunk_index=chunk_index, key=key)
        return True
    except Exception:
        await callback(request_id, status="failed")
        return False
