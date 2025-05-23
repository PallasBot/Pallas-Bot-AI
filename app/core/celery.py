from celery import Celery

from app.core.config import settings

celery_app = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)

celery_app.autodiscover_tasks(["app.tasks"])

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    worker_pool="threads",
    worker_concurrency=4,
)
