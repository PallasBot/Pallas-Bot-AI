import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import sing as sing_mod


def test_sing_routes_to_media_queue(monkeypatch) -> None:
    pytest.importorskip("app.tasks.sing.sing_tasks")

    apply_async = MagicMock(return_value=SimpleNamespace(id="celery-sing-1"))
    monkeypatch.setattr(sing_mod, "ensure_sing_worker", lambda: None)
    monkeypatch.setattr("app.tasks.sing.sing_task.apply_async", apply_async)

    task_id = asyncio.run(sing_mod.sing("req-1", "amiya", 123, 0, 0, 30))

    assert task_id == "celery-sing-1"
    _, kwargs = apply_async.call_args
    assert kwargs["queue"] == "media"


def test_play_routes_to_media_queue(monkeypatch) -> None:
    pytest.importorskip("app.tasks.sing.sing_tasks")

    apply_async = MagicMock(return_value=SimpleNamespace(id="celery-play-1"))
    monkeypatch.setattr(sing_mod, "ensure_sing_worker", lambda: None)
    monkeypatch.setattr("app.tasks.sing.play_task.apply_async", apply_async)

    request_id = asyncio.run(sing_mod.play("req-play-1", "amiya"))

    assert request_id == "req-play-1"
    _, kwargs = apply_async.call_args
    assert kwargs["queue"] == "media"


def test_download_routes_to_media_queue(monkeypatch) -> None:
    pytest.importorskip("app.tasks.sing.sing_tasks")

    apply_async = MagicMock(return_value=SimpleNamespace(id="celery-request-1"))
    monkeypatch.setattr(sing_mod, "ensure_sing_worker", lambda: None)
    monkeypatch.setattr("app.tasks.sing.request_task.apply_async", apply_async)

    task_id = asyncio.run(sing_mod.download("req-2", 456))

    assert task_id == "celery-request-1"
    _, kwargs = apply_async.call_args
    assert kwargs["queue"] == "media"
