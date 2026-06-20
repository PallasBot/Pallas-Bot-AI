import asyncio
import time
from pathlib import Path

import anyio
from apscheduler.schedulers.background import BackgroundScheduler
from asyncer import asyncify

from app.core.celery import celery_app
from app.core.config import settings
from app.core.logger import log_id_suffix, logger, task_log
from app.services.callback import callback
from app.utils.gpu_locker import get_gpu_locker

from .mixer import mix, splice
from .ncm_loader import download
from .separater import separate
from .slicer import slice as slice_audio
from .svc_inference import inference

gpu_locker = get_gpu_locker(settings.sing_cuda_device)


async def sing_audio_callback(
    request_id: str,
    audio: bytes,
    song_id: int,
    chunk_index: int,
    key: int,
) -> None:
    await callback(
        request_id,
        audio=audio,
        song_id=str(song_id),
        chunk_index=chunk_index,
        key=key,
    )


def spliced_chunk_index(path: Path) -> int | None:
    for part in path.stem.split("_"):
        if part.startswith("spliced"):
            try:
                return int(part.replace("spliced", ""))
            except ValueError:
                return None
    return None


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


@celery_app.task(name="sing")
def sing_task(request_id: str, speaker: str, song_id: int, sing_length: int, chunk_index: int, key: int):
    return run_celery_async(_sing_task_async(request_id, speaker, song_id, sing_length, chunk_index, key))


async def _sing_task_async(request_id: str, speaker: str, song_id: int, sing_length: int, chunk_index: int, key: int):
    # 下载 -> 切片 -> 人声分离 -> 音色转换（SVC） -> 混音
    # 其中 人声分离和音色转换是吃 GPU 的，所以要加锁，不然显存不够用
    task_log(
        "sing task started{} speaker={} song_id={} sing_length={} chunk_index={} key={}",
        log_id_suffix(request_id),
        speaker,
        song_id,
        sing_length,
        chunk_index,
        key,
    )

    if chunk_index == 0:
        for cache_path in Path("resource/sing/splices").glob(f"{song_id}_*_{key}key_{speaker}.mp3"):
            if cache_path.name.startswith(f"{song_id}_full_"):
                task_log(
                    "sing task hit full cache{} path={} song_id={} key={} speaker={}",
                    log_id_suffix(request_id),
                    cache_path,
                    song_id,
                    key,
                    speaker,
                )
                async with await anyio.open_file(cache_path, "rb") as f:
                    file = await f.read()
                    task_log(
                        "sing task sending cached full callback{} path={} bytes={}",
                        log_id_suffix(request_id),
                        cache_path,
                        len(file),
                    )
                    await sing_audio_callback(request_id, file, song_id, 0, key)
                return True
            elif cache_path.name.startswith(f"{song_id}_spliced"):
                task_log(
                    "sing task hit spliced cache{} path={} song_id={} key={} speaker={}",
                    log_id_suffix(request_id),
                    cache_path,
                    song_id,
                    key,
                    speaker,
                )
                async with await anyio.open_file(cache_path, "rb") as f:
                    file = await f.read()
                cached_chunk = spliced_chunk_index(cache_path)
                task_log(
                    "sing task sending cached chunk callback{} path={} bytes={} cached_chunk={}",
                    log_id_suffix(request_id),
                    cache_path,
                    len(file),
                    cached_chunk,
                )
                if cached_chunk is None:
                    await sing_audio_callback(request_id, file, song_id, chunk_index, key)
                else:
                    await sing_audio_callback(request_id, file, song_id, cached_chunk, key)
                return True
    else:
        cache_path = Path("resource/sing/mix") / f"{song_id}_chunk{chunk_index}_{key}key_{speaker}.mp3"
        if cache_path.exists():
            task_log(
                "sing task hit mix cache{} path={} song_id={} chunk_index={} key={} speaker={}",
                log_id_suffix(request_id),
                cache_path,
                song_id,
                chunk_index,
                key,
                speaker,
            )
            await asyncify(splice)(
                cache_path, Path("resource/sing/splices"), False, song_id, chunk_index, speaker, key=key
            )
            async with await anyio.open_file(cache_path, "rb") as f:
                file = await f.read()
            task_log(
                "sing task sending cached mix callback{} path={} bytes={}",
                log_id_suffix(request_id),
                cache_path,
                len(file),
            )
            await sing_audio_callback(request_id, file, song_id, chunk_index, key)
            return True

    # 从网易云下载
    task_log("sing task downloading source{} song_id={}", log_id_suffix(request_id), song_id)
    origin = await download(song_id)
    if not origin:
        logger.error("sing task download failed{} song_id={}", log_id_suffix(request_id), song_id)
        await callback(request_id, status="failed")
        return False
    task_log("sing task download completed{} song_id={} path={}", log_id_suffix(request_id), song_id, origin)

    # 音频切片
    task_log("sing task slicing audio{} origin={} size_ms={}", log_id_suffix(request_id), origin, sing_length * 1000)
    slices_list = await asyncify(slice_audio)(origin, Path("resource/sing/slices"), song_id, size_ms=sing_length * 1000)
    if not slices_list or chunk_index >= len(slices_list):
        if chunk_index == len(slices_list):
            await asyncify(splice)(
                Path("NotExists"), Path("resource/sing/splices"), True, song_id, chunk_index, speaker, key=key
            )
        logger.error(
            "sing task slice failed{} song_id={} chunk_index={} slices_count={}",
            log_id_suffix(request_id),
            song_id,
            chunk_index,
            0 if not slices_list else len(slices_list),
        )
        await callback(request_id, status="failed")
        return False

    chunk = slices_list[chunk_index]
    task_log(
        "sing task selected chunk{} song_id={} chunk_index={} total_chunks={} path={}",
        log_id_suffix(request_id),
        song_id,
        chunk_index,
        len(slices_list),
        chunk,
    )

    # 人声分离
    task_log("sing task separating vocals{} chunk={} key={}", log_id_suffix(request_id), chunk, key)
    separated = await asyncify(separate)(chunk, Path("resource/sing"), locker=gpu_locker, key=key)
    if not separated:
        logger.error(
            "sing task separate failed{} song_id={} chunk_index={} chunk={} key={}",
            log_id_suffix(request_id),
            song_id,
            chunk_index,
            chunk,
            key,
        )
        await callback(request_id, status="failed")
        return False

    vocals, no_vocals = separated
    task_log(
        "sing task separate completed{} vocals={} no_vocals={}",
        log_id_suffix(request_id),
        vocals,
        no_vocals,
    )

    # 音色转换（SVC）
    task_log(
        "sing task running svc{} vocals={} speaker={} key={}",
        log_id_suffix(request_id),
        vocals,
        speaker,
        key,
    )
    svc = await asyncify(inference)(vocals, Path("resource/sing/svc"), key=key, speaker=speaker, locker=gpu_locker)
    if not svc:
        logger.error(
            "sing task svc failed{} song_id={} chunk_index={} vocals={} speaker={} key={}",
            log_id_suffix(request_id),
            song_id,
            chunk_index,
            vocals,
            speaker,
            key,
        )
        await callback(request_id, status="failed")
        return False
    task_log("sing task svc completed{} output={}", log_id_suffix(request_id), svc)

    # 混合人声和伴奏
    task_log(
        "sing task mixing audio{} svc={} no_vocals={} vocals={}",
        log_id_suffix(request_id),
        svc,
        no_vocals,
        vocals,
    )
    result = await asyncify(mix)(svc, no_vocals, vocals, Path("resource/sing/mix"), svc.stem)
    if not result:
        logger.error(
            "sing task mix failed{} song_id={} chunk_index={} svc={}",
            log_id_suffix(request_id),
            song_id,
            chunk_index,
            svc,
        )
        await callback(request_id, status="failed")
        return False
    task_log("sing task mix completed{} result={}", log_id_suffix(request_id), result)

    # 混音后合并混音结果
    finished = chunk_index == len(slices_list) - 1
    task_log(
        "sing task splicing result{} result={} finished={} chunk_index={}",
        log_id_suffix(request_id),
        result,
        finished,
        chunk_index,
    )
    await asyncify(splice)(result, Path("resource/sing/splices"), finished, song_id, chunk_index, speaker, key=key)
    async with await anyio.open_file(result, "rb") as f:
        file = await f.read()
    task_log(
        "sing task sending callback{} result={} bytes={} song_id={} chunk_index={} key={}",
        log_id_suffix(request_id),
        result,
        len(file),
        song_id,
        chunk_index,
        key,
    )
    await sing_audio_callback(request_id, file, song_id, chunk_index, key)
    task_log("sing task completed{} song_id={} chunk_index={} key={}", log_id_suffix(request_id), song_id, chunk_index, key)
    return True


@celery_app.task(name="request")
def request_task(request_id: str, song_id: int):
    return run_celery_async(_request_task_async(request_id, song_id))


async def _request_task_async(request_id: str, song_id: int):
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
        await callback(request_id, audio=file)

    task_log("request task completed{} song_id={} path={}", log_id_suffix(request_id), song_id, origin)
    return True


SONG_PATH = "resource/sing/splices/"
MUSIC_PATH = "resource/music/"

cleanup_sched = BackgroundScheduler()


@cleanup_sched.scheduled_job("cron", hour=4, minute=15)
def cleanup_cache():
    logger.info("cleaning up cache...")

    cache_size = settings.song_cache_size
    cache_days = settings.song_cache_days
    current_time = time.time()
    song_atime = {}

    for file_path in Path(SONG_PATH).glob("**/*.*"):
        try:
            last_access_time = file_path.stat().st_atime
        except OSError:
            continue
        song_atime[file_path] = last_access_time
    # 只保留最近最多 cache_size 首歌
    recent_songs = sorted(song_atime, key=song_atime.get, reverse=True)[:cache_size]

    prefix_path = "resource/sing"
    cache_dirs = [Path(prefix_path, suffix) for suffix in ["hdemucs_mmi", "mix", "ncm", "slices", "splices", "svc"]]
    removed_files = 0

    for dir_path in cache_dirs:
        for file_path in dir_path.glob("**/*.*"):
            if file_path in recent_songs:
                continue
            try:
                last_access_time = file_path.stat().st_atime
            except OSError:
                continue
            # 清理超过 cache_days 天未访问的文件
            if (current_time - last_access_time) > (24 * 60 * 60) * cache_days:
                file_path.unlink()
                removed_files += 1

    logger.info(f"cleaned up {removed_files} files.")
