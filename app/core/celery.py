from celery import Celery
from celery.signals import worker_ready

from app.core.config import settings
from app.core.ollama_runtime import ensure_ollama_ready_sync

celery_app = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)

celery_app.autodiscover_tasks(["app.tasks"])


@worker_ready.connect
def on_celery_worker_ready(**kwargs):
    ensure_ollama_ready_sync()


celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    worker_pool="threads",
    worker_concurrency=4,
    broker_connection_retry_on_startup=True,
)
