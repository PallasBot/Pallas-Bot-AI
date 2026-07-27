"""媒体能力统一门面：HTTP 与 Celery 经此入队，便于后续接云端 Backend。

TTS 不经此模块再导出，避免无 TTS 依赖安装时拖垮 sing 路由加载。
"""

from app.media.runtime import (
    clear_media_task_runtime,
    get_media_task,
    media_task_runtime_status,
    submit_media_task,
)
from app.media.services.sing import download, play, sing

__all__ = [
    "clear_media_task_runtime",
    "download",
    "get_media_task",
    "media_task_runtime_status",
    "play",
    "sing",
    "submit_media_task",
]
