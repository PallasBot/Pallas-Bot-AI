from io import StringIO
from types import SimpleNamespace

import redis
from loguru import logger

from app.core import celery
from app.core import redis_client as redis_client_module


def test_celery_startup_does_not_log_redis_credentials(monkeypatch) -> None:
    redis_url = "redis://url-user:url-password@redis.invalid:6379/0"
    exception_url = "redis://error-user:error-password@redis.invalid:6379/0"
    output = StringIO()

    def fail_ping() -> None:
        raise redis.ConnectionError(f"unable to connect to {exception_url}")

    monkeypatch.setattr(celery.settings, "redis_url", redis_url)
    monkeypatch.setattr(redis_client_module, "redis_client", lambda: SimpleNamespace(ping=fail_ping))
    monkeypatch.setattr(celery, "start_sing_cleanup_scheduler", lambda: None)
    monkeypatch.setattr(celery, "sweep_gpu_lock_state_on_worker_startup", lambda: None)
    monkeypatch.setattr(celery, "register_startup_fact", lambda *args: None)
    monkeypatch.setattr(celery, "register_startup_warning", lambda *args: None)
    monkeypatch.setattr(celery, "emit_startup_summary", lambda **kwargs: None)

    sink_id = logger.add(output, level="ERROR")
    try:
        celery.on_celery_worker_ready()
    finally:
        logger.remove(sink_id)

    message = output.getvalue()
    assert "Redis unreachable" in message
    assert "redis://" not in message
    assert "url-password" not in message
    assert "error-password" not in message
