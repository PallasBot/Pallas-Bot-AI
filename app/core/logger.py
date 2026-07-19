from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger as loguru_logger

from app.core.config import settings

# 框架与第三方库默认 WARNING；DEBUG/TRACE 时不压制以便排障
_QUIET_LOGGER_NAMES = (
    "uvicorn",
    "uvicorn.access",
    "uvicorn.error",
    "uvicorn.asgi",
    "celery",
    "celery.worker",
    "celery.worker.strategy",
    "celery.worker.consumer",
    "celery.worker.consumer.connection",
    "celery.worker.consumer.mingle",
    "celery.apps.worker",
    "celery.app.trace",
    "celery.redirected",
    "kombu",
    "amqp",
    "billiard",
    "asyncio",
    "httpx",
    "httpcore",
    "watchfiles",
    "aiohttp",
    "aiohttp.access",
    "aiohttp.client",
    "aiohttp.server",
    "aiohttp.web",
    "apscheduler",
    "apscheduler.scheduler",
    "PIL",
    "PIL.PngImagePlugin",
    "urllib3",
    "urllib3.connectionpool",
    "multipart",
    "fontTools",
    "aiosqlite",
)

_MODULE_ALIASES = (
    ("app.api.", "ai.api"),
    ("app.providers.", "ai.providers"),
    ("app.services.", "ai.service"),
    ("app.tasks.", "ai.task"),
    ("app.core.", "ai.core"),
    ("app.", "ai"),
    ("uvicorn.", "uvicorn"),
    ("celery.", "celery"),
    ("httpx", "httpx"),
    ("httpcore", "httpx"),
)


def module_display_name(name: str) -> str:
    text = str(name or "").strip()
    for prefix, alias in _MODULE_ALIASES:
        if text == prefix.rstrip(".") or text.startswith(prefix):
            return alias
    return text.rsplit(".", 1)[-1] or text


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)
        frame = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        label = module_display_name(record.name)
        text = record.getMessage()
        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level,
            f"[{label}] {text}" if label else text,
        )


def resolve_log_level(name: str, *, fallback: str = "INFO") -> str:
    text = str(name or "").strip().upper()
    if text in {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}:
        return text
    return fallback


def stdlib_level(name: str, *, fallback: str = "INFO") -> int:
    text = resolve_log_level(name, fallback=fallback)
    return int(getattr(logging, text, getattr(logging, fallback, logging.INFO)))


def short_log_id(value: str | None) -> str:
    """按 LOG_ID_CHARS 截断任务/请求 ID；0 表示省略。"""
    text = str(value or "").strip()
    if not text:
        return ""
    limit = int(settings.log_id_chars)
    if limit <= 0:
        return ""
    return text[:limit] if len(text) > limit else text


def log_id_clause(value: str | None, *, label: str = "单号") -> str:
    """返回可拼进日志的前缀，如「单号=01KV95T5 」；省略时返回空串。"""
    short = short_log_id(value)
    if not short:
        return ""
    return f"{label}={short} "


def log_id_suffix(value: str | None, *, label: str = "单号", prefix: str = " ") -> str:
    """附在句末的 ID 片段，如「 单号=01KV95T5」；省略时返回空串。"""
    short = short_log_id(value)
    if not short:
        return ""
    return f"{prefix}{label}={short}"


def task_log(message: str, *args, **kwargs) -> None:
    level = "INFO" if settings.log_verbose_tasks else "DEBUG"
    loguru_logger.log(level, message, *args, **kwargs)


def configure_stdlib_logging() -> None:
    """接入 stdlib logging。"""
    app_level = resolve_log_level(settings.log_level, fallback="INFO")
    server_level_no = stdlib_level(settings.server_log_level, fallback="WARNING")

    logging.root.handlers = [InterceptHandler()]
    logging.root.setLevel(server_level_no)

    if app_level in {"DEBUG", "TRACE"}:
        return

    for name in _QUIET_LOGGER_NAMES:
        logging.getLogger(name).setLevel(server_level_no)


def patch_log_record(record: dict) -> None:
    name = str(record.get("name") or "")
    module = module_display_name(name)
    record["extra"]["loc"] = f"{module}:{record['line']}"


def effective_log_format() -> str:
    if settings.log_loc_short:
        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <7}</level> | "
            "<cyan>{extra[loc]:<16}</cyan> | "
            "<level>{message}</level>"
        )
    return settings.log_format


def configure_logger():
    """初始化 Loguru 配置"""

    loguru_logger.remove()
    loguru_logger.configure(patcher=patch_log_record)

    app_level = resolve_log_level(settings.log_level, fallback="INFO")
    log_format = effective_log_format()
    loguru_logger.add(sys.stderr, level=app_level, format=log_format)

    if settings.log_file_enabled:
        log_path = Path(settings.log_path)
        log_path.mkdir(exist_ok=True)

        loguru_logger.add(
            log_path / "app.log",
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            compression=settings.log_compression,
            level=app_level,
            format=log_format,
            filter=lambda record: "access" not in record["extra"],
        )

        access_logger = loguru_logger.bind(access=True)
        access_logger.add(
            log_path / "access.log",
            rotation=settings.log_rotation,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
            filter=lambda record: "access" in record["extra"],
        )

    configure_stdlib_logging()
    return loguru_logger


logger = configure_logger()
