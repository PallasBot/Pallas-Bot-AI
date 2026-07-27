"""AI 服务落盘日志路径解析与尾部读取。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from app.core.config import settings

ServiceLogKind = Literal["uvicorn", "celery", "celery-media"]

LOG_KIND_FILENAMES: dict[ServiceLogKind, tuple[str, ...]] = {
    "uvicorn": ("uvicorn.log", "api.log", "app.log"),
    "celery": ("celery.log",),
    "celery-media": ("celery-media.log",),
}


def logs_dir() -> Path:
    return Path(settings.log_path).resolve()


def resolve_service_log_path(kind: ServiceLogKind) -> Path | None:
    names = LOG_KIND_FILENAMES.get(kind)
    if not names:
        return None
    base = logs_dir()
    for name in names:
        candidate = base / name
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return (base / names[0]).resolve()


def tail_log_lines(path: Path, n: int, *, max_tail_bytes: int = 256_000) -> list[str]:
    """读取日志尾部最近 n 行；大文件只读末尾 max_tail_bytes。"""
    count = max(1, min(int(n), 2000))
    try:
        size = path.stat().st_size
    except OSError:
        return []
    try:
        with path.open("rb") as fh:
            if size > max_tail_bytes:
                fh.seek(size - max_tail_bytes)
                raw = fh.read()
                nl = raw.find(b"\n")
                if nl >= 0:
                    raw = raw[nl + 1 :]
            else:
                raw = fh.read()
    except OSError:
        return []
    if not raw:
        return []
    text = raw.decode("utf-8", errors="ignore")
    return text.splitlines()[-count:]
