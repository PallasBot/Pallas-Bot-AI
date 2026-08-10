from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from operator import itemgetter
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.logger import logger
from app.media.models import get_sing_defaults

CACHE_STAGES = ("hdemucs_mmi", "mix", "ncm", "slices", "splices", "svc")
SHANGHAI = ZoneInfo("Asia/Shanghai")
SONG_KEY_PATTERN = re.compile(r"^(\d+)(?:_|\.|$)")


@dataclass
class CleanupResult:
    scanned: int = 0
    removed: list[Path] = field(default_factory=list)
    protected: list[Path] = field(default_factory=list)
    failed: list[Path] = field(default_factory=list)
    protected_song_keys: tuple[str, ...] = ()


def song_key(path: Path, root: Path) -> str | None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    candidates = [path.name]
    if relative.parts and relative.parts[0] == "hdemucs_mmi" and len(relative.parts) > 1:
        candidates.insert(0, relative.parts[1])
    for candidate in candidates:
        match = SONG_KEY_PATTERN.match(candidate)
        if match:
            return match.group(1)
    return None


def cleanup_cache(*, root: Path = Path("resource/sing"), now: datetime | None = None) -> CleanupResult:
    policy = get_sing_defaults()
    cache_days = int(policy["song_cache_days"])
    cache_size = int(policy["song_cache_size"])
    current_time = (now or datetime.now(SHANGHAI)).timestamp()
    result = CleanupResult()
    files: list[tuple[Path, float, str | None]] = []
    song_access: dict[str, float] = {}

    for stage in CACHE_STAGES:
        for path in (root / stage).glob("**/*.*"):
            result.scanned += 1
            try:
                atime = path.stat().st_atime
            except OSError as exc:
                result.failed.append(path)
                logger.warning("sing cache stat failed: path={} error={}", path, exc)
                continue
            key = song_key(path, root)
            files.append((path, atime, key))
            if key is not None:
                song_access[key] = max(song_access.get(key, 0.0), atime)

    protected_keys = (
        tuple(key for key, _atime in sorted(song_access.items(), key=itemgetter(1), reverse=True)[:cache_size])
        if cache_size
        else ()
    )
    protected_set = set(protected_keys)
    result.protected_song_keys = protected_keys
    max_age = cache_days * 86400

    for path, atime, key in files:
        if key is not None and key in protected_set:
            result.protected.append(path)
            continue
        if current_time - atime <= max_age:
            continue
        try:
            path.unlink()
        except OSError as exc:
            result.failed.append(path)
            logger.warning("sing cache unlink failed: path={} error={}", path, exc)
            continue
        result.removed.append(path)

    logger.info(
        "sing cache cleanup completed: scanned={} removed={} protected={} failed={} days={} size={}",
        result.scanned,
        len(result.removed),
        len(result.protected),
        len(result.failed),
        cache_days,
        cache_size,
    )
    return result


cleanup_scheduler = BackgroundScheduler(timezone=SHANGHAI)
cleanup_scheduler.add_job(
    cleanup_cache,
    "cron",
    hour=4,
    minute=15,
    id="sing-cache-cleanup",
    replace_existing=True,
)
