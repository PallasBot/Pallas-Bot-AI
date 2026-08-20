from celery import Celery
from celery.signals import setup_logging, worker_ready, worker_shutdown
from kombu import Exchange, Queue

from app.core.config import settings
from app.core.logger import configure_stdlib_logging, logger
from app.core.redis_client import ping_redis_sync
from app.core.startup_report import emit_startup_summary, register_startup_fact, register_startup_warning
from app.utils.gpu_locker import sweep_gpu_lock_state_on_worker_startup
from app.version import VERSION

celery_app = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)

_TASK_PACKAGE_ALIASES = {
    "chat": "app.workers.chat",
    "fast": "app.workers.fast",
    "sing": "app.workers.sing",
    "tts": "app.workers.tts",
}

_DEFAULT_TASK_PACKAGES = ["app.workers.sing", "app.workers.tts", "app.workers.chat"]

# GPU 写锁串行的重任务留在 media；随机播放/点歌不吃 GPU，走独立 fast 队列，
# 避免被翻唱/TTS 长任务堵在队列里。
_TASK_QUEUE_ROUTES = {
    "chat": "media",
    "sing": "media",
    "tts": "media",
    "play": "fast",
    "request": "fast",
}


def resolve_celery_task_packages(raw: str | None = None) -> list[str]:
    text = str(raw if raw is not None else settings.celery_task_packages or "sing,tts,chat").strip().lower()
    if not text or text in ("all", "*", "media"):
        return list(_DEFAULT_TASK_PACKAGES)
    packages: list[str] = []
    for part in text.replace(";", ",").split(","):
        name = part.strip().lower()
        if not name:
            continue
        resolved = _TASK_PACKAGE_ALIASES.get(name, name if name.startswith("app.workers.") else "")
        if resolved and resolved not in packages:
            packages.append(resolved)
    return packages or list(_DEFAULT_TASK_PACKAGES)


def celery_task_package_enabled(alias: str) -> bool:
    name = (alias or "").strip().lower()
    package = _TASK_PACKAGE_ALIASES.get(name)
    if not package:
        return False
    return package in resolve_celery_task_packages()


def require_celery_task_package(alias: str) -> None:
    if celery_task_package_enabled(alias):
        return
    raise RuntimeError(
        f"任务队列未注册 {alias}：请在 .env 设置 CELERY_TASK_PACKAGES=all 或包含 {alias}，并重启后台任务进程"
    )


def resolve_celery_queue_for_task(task_name: str, default: str = "media") -> str:
    name = str(task_name or "").strip()
    return _TASK_QUEUE_ROUTES.get(name, default)


def celery_queue_names() -> tuple[str, ...]:
    """已注册的 Celery 队列名（供部署脚本 / 运维确认队列一致性）。"""
    return tuple(sorted(set(_TASK_QUEUE_ROUTES.values()) | {"default"}))


sing_cleanup_scheduler = None


def get_sing_cleanup_scheduler():
    if sing_cleanup_scheduler is not None:
        return sing_cleanup_scheduler
    from app.workers.sing.cache_cleanup import cleanup_scheduler  # noqa: PLC0415

    return cleanup_scheduler


def start_sing_cleanup_scheduler() -> None:
    if not celery_task_package_enabled("sing"):
        return
    try:
        scheduler = get_sing_cleanup_scheduler()
        if not scheduler.running:
            scheduler.start()
            logger.info("sing cache cleanup scheduler started")
    except Exception as exc:
        logger.exception("sing cache cleanup scheduler failed to start: {}", exc)


def stop_sing_cleanup_scheduler() -> None:
    if not celery_task_package_enabled("sing"):
        return
    try:
        scheduler = get_sing_cleanup_scheduler()
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("sing cache cleanup scheduler stopped")
    except Exception as exc:
        logger.exception("sing cache cleanup scheduler failed to stop: {}", exc)


celery_app.autodiscover_tasks(resolve_celery_task_packages())


@setup_logging.connect
def on_celery_setup_logging(**kwargs):
    configure_stdlib_logging()


@worker_ready.connect
def on_celery_worker_ready(**kwargs):
    start_sing_cleanup_scheduler()
    sweep_gpu_lock_state_on_worker_startup()
    register_startup_fact("concurrency", str(settings.celery_worker_concurrency))
    if not ping_redis_sync():
        register_startup_warning("redis", "unreachable")
        logger.error(
            "Redis unreachable at [{}]; task queue and media task status depend on it",
            settings.redis_url,
        )
    register_startup_fact("packages", ",".join(resolve_celery_task_packages()))
    emit_startup_summary(api_version=VERSION, role="celery")


@worker_shutdown.connect
def on_celery_worker_shutdown(**kwargs):
    stop_sing_cleanup_scheduler()


celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_queues=(
        Queue("default"),
        Queue("media"),
        # fast 必须显式绑定独立 exchange/routing_key，否则会继承 task_default_queue=media，
        # 与 media 队列绑定相同导致轻任务被重复投递到 media 队列。
        Queue("fast", Exchange("fast"), routing_key="fast"),
    ),
    task_routes={task_name: {"queue": queue} for task_name, queue in _TASK_QUEUE_ROUTES.items()},
    task_track_started=True,
    worker_pool="threads",
    worker_concurrency=settings.celery_worker_concurrency,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_time_limit=settings.celery_task_time_limit,
    worker_soft_shutdown_timeout=settings.celery_worker_soft_shutdown_timeout,
    broker_pool_limit=50,
    redis_max_connections=50,
    worker_max_tasks_per_child=1000,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    worker_disable_rate_limits=True,
    worker_hijack_root_logger=False,
    task_default_queue="media",
)
