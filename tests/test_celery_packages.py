from app.core.celery import celery_task_package_enabled, resolve_celery_task_packages


def test_resolve_celery_task_packages_default_llm() -> None:
    assert resolve_celery_task_packages("llm") == ["app.tasks.llm"]


def test_resolve_celery_task_packages_all() -> None:
    packages = resolve_celery_task_packages("all")
    assert "app.tasks.llm" in packages
    assert "app.tasks.chat" in packages


def test_resolve_celery_task_packages_multi() -> None:
    assert resolve_celery_task_packages("llm,chat") == ["app.tasks.llm", "app.tasks.chat"]


def test_celery_task_package_enabled(monkeypatch) -> None:
    monkeypatch.setattr("app.core.celery.settings.celery_task_packages", "llm")
    assert celery_task_package_enabled("llm") is True
    assert celery_task_package_enabled("sing") is False

    monkeypatch.setattr("app.core.celery.settings.celery_task_packages", "llm,sing")
    assert celery_task_package_enabled("sing") is True
