from celery import Celery
from celery.signals import setup_logging, worker_ready
from kombu import Queue

from app.core.config import settings
from app.core.llm_backend_runtime import get_llm_model, prepare_local_backend_for_worker_sync
from app.core.logger import configure_stdlib_logging, logger
from app.core.startup_report import emit_startup_summary, register_startup_fact, register_startup_warning
from app.services.llm_task_metrics import start_background_flush
from app.session import normalize_session_backend
from app.session.redis_store import ping_redis_sync

celery_app = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)

_TASK_PACKAGE_ALIASES = {
    "llm": "app.tasks.llm",
    "chat": "app.tasks.chat",
    "sing": "app.tasks.sing",
    "tts": "app.tasks.tts",
}

_TASK_QUEUE_ROUTES = {
    "llm_chat": "default",
    "llm_del_session": "default",
    "unload_local_backend_model": "default",
    "chat": "media",
    "sing": "media",
    "play": "media",
    "request": "media",
    "tts": "media",
}


def resolve_celery_task_packages(raw: str | None = None) -> list[str]:
    text = str(raw if raw is not None else settings.celery_task_packages or "llm").strip().lower()
    if not text or text in ("all", "*"):
        return list(_TASK_PACKAGE_ALIASES.values())
    packages: list[str] = []
    for part in text.replace(";", ",").split(","):
        name = part.strip().lower()
        if not name:
            continue
        resolved = _TASK_PACKAGE_ALIASES.get(name, name if name.startswith("app.tasks.") else "")
        if resolved and resolved not in packages:
            packages.append(resolved)
    return packages or [_TASK_PACKAGE_ALIASES["llm"]]


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


def resolve_celery_queue_for_task(task_name: str, default: str = "default") -> str:
    name = str(task_name or "").strip()
    return _TASK_QUEUE_ROUTES.get(name, default)


celery_app.autodiscover_tasks(resolve_celery_task_packages())


@setup_logging.connect
def on_celery_setup_logging(**kwargs):
    configure_stdlib_logging()


@worker_ready.connect
def on_celery_worker_ready(**kwargs):
    session_backend = normalize_session_backend(settings.llm_session_backend)
    register_startup_fact("concurrency", str(settings.celery_worker_concurrency))
    register_startup_fact("session", session_backend)
    if session_backend == "redis" and not ping_redis_sync():
        register_startup_warning("redis", "unreachable")
        logger.error("Redis 不可达：{}（任务队列与 LLM 会话依赖此项）", settings.redis_url)
    if settings.llm_chat_enabled:
        prepare_local_backend_for_worker_sync()
        register_startup_fact("llm_model", get_llm_model())
    register_startup_fact("packages", ",".join(resolve_celery_task_packages()))
    emit_startup_summary(api_version="4.0.0", role="celery")
    start_background_flush()


celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_queues=(
        Queue("default"),
        Queue("media"),
    ),
    task_routes={task_name: {"queue": queue} for task_name, queue in _TASK_QUEUE_ROUTES.items()},
    task_track_started=True,
    worker_pool="threads",
    worker_concurrency=settings.celery_worker_concurrency,
    worker_prefetch_multiplier=1,
    # soft 超时抛 SoftTimeLimitExceeded；threads 池下 hard 无法打断 GPU 阻塞，靠 gpu_locker 兜底
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
    task_default_queue="default",
)
