from app.core.celery import (
    celery_task_package_enabled,
    resolve_celery_queue_for_task,
    resolve_celery_task_packages,
)


def test_resolve_celery_task_packages_default_media() -> None:
    assert resolve_celery_task_packages("sing,tts,chat") == [
        "app.tasks.sing",
        "app.tasks.tts",
        "app.tasks.chat",
    ]


def test_resolve_celery_task_packages_all() -> None:
    packages = resolve_celery_task_packages("all")
    assert "app.tasks.chat" in packages
    assert "app.tasks.sing" in packages


def test_resolve_celery_task_packages_multi() -> None:
    assert resolve_celery_task_packages("sing,chat") == ["app.tasks.sing", "app.tasks.chat"]


def test_celery_task_package_enabled(monkeypatch) -> None:
    monkeypatch.setattr("app.core.celery.settings.celery_task_packages", "sing")
    assert celery_task_package_enabled("sing") is True
    assert celery_task_package_enabled("tts") is False

    monkeypatch.setattr("app.core.celery.settings.celery_task_packages", "sing,tts")
    assert celery_task_package_enabled("tts") is True


def test_resolve_celery_queue_for_task() -> None:
    assert resolve_celery_queue_for_task("chat") == "media"
    assert resolve_celery_queue_for_task("sing") == "media"
    assert resolve_celery_queue_for_task("play") == "media"
    assert resolve_celery_queue_for_task("request") == "media"
    assert resolve_celery_queue_for_task("tts") == "media"
    assert resolve_celery_queue_for_task("unknown") == "media"
