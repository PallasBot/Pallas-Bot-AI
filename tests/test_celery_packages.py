from app.core import celery as celery_module
from app.core.celery import (
    celery_task_package_enabled,
    resolve_celery_queue_for_task,
    resolve_celery_task_packages,
)


def test_resolve_celery_task_packages_default_media() -> None:
    assert resolve_celery_task_packages("sing,tts,chat") == [
        "app.workers.sing",
        "app.workers.tts",
        "app.workers.chat",
    ]


def test_resolve_celery_task_packages_all() -> None:
    packages = resolve_celery_task_packages("all")
    assert "app.workers.chat" in packages
    assert "app.workers.sing" in packages


def test_resolve_celery_task_packages_multi() -> None:
    assert resolve_celery_task_packages("sing,chat") == ["app.workers.sing", "app.workers.chat"]


def test_celery_task_package_enabled(monkeypatch) -> None:
    monkeypatch.setattr("app.core.celery.settings.celery_task_packages", "sing")
    assert celery_task_package_enabled("sing") is True
    assert celery_task_package_enabled("tts") is False

    monkeypatch.setattr("app.core.celery.settings.celery_task_packages", "sing,tts")
    assert celery_task_package_enabled("tts") is True


def test_sing_cleanup_scheduler_lifecycle(monkeypatch) -> None:
    calls: list[str] = []
    scheduler = type(
        "Scheduler",
        (),
        {
            "running": False,
            "start": lambda self: (calls.append("start"), setattr(self, "running", True)),
            "shutdown": lambda self, wait=False: (calls.append(f"stop:{wait}"), setattr(self, "running", False)),
        },
    )()
    monkeypatch.setattr(celery_module, "sing_cleanup_scheduler", scheduler)
    monkeypatch.setattr(celery_module, "celery_task_package_enabled", lambda alias: alias == "sing")

    celery_module.start_sing_cleanup_scheduler()
    celery_module.start_sing_cleanup_scheduler()
    celery_module.stop_sing_cleanup_scheduler()
    celery_module.stop_sing_cleanup_scheduler()
    assert calls == ["start", "stop:False"]


def test_sing_cleanup_scheduler_not_started_when_package_disabled(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(celery_module, "celery_task_package_enabled", lambda _alias: False)
    monkeypatch.setattr(celery_module, "get_sing_cleanup_scheduler", lambda: calls.append("load"))

    celery_module.start_sing_cleanup_scheduler()
    celery_module.stop_sing_cleanup_scheduler()
    assert calls == []


def test_resolve_celery_queue_for_task() -> None:
    assert resolve_celery_queue_for_task("chat") == "media"
    assert resolve_celery_queue_for_task("sing") == "media"
    assert resolve_celery_queue_for_task("play") == "media"
    assert resolve_celery_queue_for_task("request") == "media"
    assert resolve_celery_queue_for_task("tts") == "media"
    assert resolve_celery_queue_for_task("unknown") == "media"
