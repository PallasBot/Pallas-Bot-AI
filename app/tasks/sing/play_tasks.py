import asyncio
import random
from pathlib import Path

import anyio

from app.core.celery import celery_app
from app.core.logger import log_id_suffix, logger
from app.services.callback import callback

SONG_PATH = "resource/sing/splices/"
MUSIC_PATH = "resource/music/"


def get_random_song(speaker: str = ""):
    all_song = []
    source = None
    song_dir = Path(SONG_PATH)
    if song_dir.exists():
        all_song = [str(s) for s in song_dir.iterdir() if speaker in s.name and "_spliced0" not in s.name]
        if all_song:
            source = "splices"

    if not all_song:
        music_dir = Path(MUSIC_PATH)
        if music_dir.exists():
            all_song = [str(s) for s in music_dir.iterdir()]
            if all_song:
                source = "music"

    if not all_song:
        return None, None
    return random.choice(all_song), source


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
        logger.info("play task started{} speaker={}", log_id_suffix(request_id), speaker or "<any>")
        rand_music, source = get_random_song(speaker)
        if not rand_music:
            logger.warning(
                "play task found no playable audio{} speaker={} splices_dir={} music_dir={}",
                log_id_suffix(request_id),
                speaker or "<any>",
                SONG_PATH,
                MUSIC_PATH,
            )
            await callback(request_id, status="failed")
            return False

        progress_kwargs: dict = {}
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
            progress_kwargs = {"song_id": song_id, "chunk_index": chunk_index, "key": key}
        logger.info(
            "play task selected audio{} speaker={} source={} path={} progress={}",
            log_id_suffix(request_id),
            speaker or "<any>",
            source or "unknown",
            rand_music,
            progress_kwargs or {},
        )

        try:
            async with await anyio.open_file(rand_music, "rb") as f:
                audio_content = await f.read()
        except Exception as exc:
            logger.exception(
                "play task failed to read audio{} path={} error={}",
                log_id_suffix(request_id),
                rand_music,
                exc,
            )
            await callback(request_id, status="failed")
            return False

        logger.info(
            "play task sending callback{} path={} bytes={} progress={}",
            log_id_suffix(request_id),
            rand_music,
            len(audio_content),
            progress_kwargs or {},
        )
        await callback(request_id, audio=audio_content, **progress_kwargs)
        logger.info("play task completed{} path={}", log_id_suffix(request_id), rand_music)
        return True
    except Exception as exc:
        logger.exception("play task failed unexpectedly{} error={}", log_id_suffix(request_id), exc)
        await callback(request_id, status="failed")
        return False
