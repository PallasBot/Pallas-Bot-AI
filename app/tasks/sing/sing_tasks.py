import time
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from asyncer import asyncify

from app.core.celery.celery_app import celery_app
from app.core.config import settings
from app.core.logger import logger
from app.services.callback import sing_failed, sing_success
from app.utils.gpu_locker import GPULockManager

from .mixer import mix, splice
from .ncm_loader import download
from .separater import separate, set_separate_cuda_devices
from .slicer import slice
from .svc_inference import inference, set_svc_cuda_devices

if settings.sing_cuda_device:
    set_separate_cuda_devices(settings.sing_cuda_device)
    set_svc_cuda_devices(settings.sing_cuda_device)


gpu_locker = GPULockManager(settings.sing_cuda_device)


@celery_app.task(name="sing")
async def sing_task(speaker: str, song_id: int, sing_length: int, chunk_index: int, key: int):
    # 下载 -> 切片 -> 人声分离 -> 音色转换（SVC） -> 混音
    # 其中 人声分离和音色转换是吃 GPU 的，所以要加锁，不然显存不够用

    if chunk_index == 0:
        for cache_path in Path("resource/sing/splices").glob(f"{song_id}_*_{key}key_{speaker}.mp3"):
            if cache_path.name.startswith(f"{song_id}_full_"):
                await sing_success(speaker, song_id, key, 114514, cache_path)
                return True
            elif cache_path.name.startswith(f"{song_id}_spliced"):
                await sing_success(
                    speaker, song_id, key, int(cache_path.name.split("_")[1].replace("spliced", "")), cache_path
                )
                return True
    else:
        cache_path = Path("resource/sing/mix") / f"{song_id}_chunk{chunk_index}_{key}key_{speaker}.mp3"
        if cache_path.exists():
            await asyncify(splice)(
                cache_path, Path("resource/sing/splices"), False, song_id, chunk_index, speaker, key=key
            )
            await sing_success(speaker, song_id, key, chunk_index, cache_path)
            return True

    # 从网易云下载
    origin = await asyncify(download)(song_id)
    if not origin:
        logger.error("download failed", song_id)
        await sing_failed()
        return False

    # 音频切片
    slices_list = await asyncify(slice)(origin, Path("resource/sing/slices"), song_id, size_ms=sing_length * 1000)
    if not slices_list or chunk_index >= len(slices_list):
        if chunk_index == len(slices_list):
            await asyncify(splice)(
                Path("NotExists"), Path("resource/sing/splices"), True, song_id, chunk_index, speaker, key=key
            )
        logger.error("slice failed", song_id)
        await sing_failed()
        return False

    chunk = slices_list[chunk_index]

    # 人声分离
    separated = await asyncify(separate)(chunk, Path("resource/sing"), locker=gpu_locker, key=key)
    if not separated:
        logger.error("separate failed", song_id)
        await sing_failed()
        return False

    vocals, no_vocals = separated

    # 音色转换（SVC）
    svc = await asyncify(inference)(vocals, Path("resource/sing/svc"), speaker=speaker, locker=gpu_locker, key=key)
    if not svc:
        logger.error("svc failed", song_id)
        await sing_failed()
        return False

    # 混合人声和伴奏
    result = await asyncify(mix)(svc, no_vocals, vocals, Path("resource/sing/mix"), svc.stem)
    if not result:
        logger.error("mix failed", song_id)
        await sing_failed()
        return False

    # 混音后合并混音结果
    finished = chunk_index == len(slices_list) - 1
    await asyncify(splice)(result, Path("resource/sing/splices"), finished, song_id, chunk_index, speaker, key=key)
    await sing_success(speaker, song_id, key, chunk_index, result)
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

    for file_path in Path(SONG_PATH).glob("**\\*.*"):
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
        for file_path in dir_path.glob("**\\*.*"):
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
