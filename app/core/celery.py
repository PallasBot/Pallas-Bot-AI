from celery import Celery
from celery.signals import worker_ready

from app.core.config import settings
from app.core.logger import logger
from app.core.ollama_runtime import ensure_ollama_ready_sync, get_ollama_model

celery_app = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)

celery_app.autodiscover_tasks(["app.tasks"])


@worker_ready.connect
def on_celery_worker_ready(**kwargs):
    logger.info("celery worker ready, checking ollama (enable={})", settings.ollama_enable)
    ensure_ollama_ready_sync()
    logger.info("celery worker ollama check finished, model={}", get_ollama_model())


celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    worker_pool="threads",
    worker_concurrency=6,
    worker_prefetch_multiplier=1,
    broker_pool_limit=50,
    redis_max_connections=50,
    worker_max_tasks_per_child=1000,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    worker_disable_rate_limits=True,
)
