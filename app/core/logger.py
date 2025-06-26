import sys
from pathlib import Path

from loguru import logger as loguru_logger

from app.core.config import settings


def configure_logger():
    """初始化 Loguru 配置"""

    # 移除默认配置
    loguru_logger.remove()

    # 控制台输出配置
    loguru_logger.add(sys.stderr, level=settings.log_level, format=settings.log_format)

    # 文件日志配置
    if settings.log_file_enabled:
        log_path = Path(settings.log_path)
        log_path.mkdir(exist_ok=True)

        loguru_logger.add(
            log_path / "app.log",
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            compression=settings.log_compression,
            level=settings.log_level,
            format=settings.log_format,
            filter=lambda record: "access" not in record["extra"],
        )

        access_logger = loguru_logger.bind(access=True)
        access_logger.add(
            log_path / "access.log",
            rotation=settings.log_rotation,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            filter=lambda record: "access" in record["extra"],
        )

    return loguru_logger


logger = configure_logger()
