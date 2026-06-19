from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.llm_queue import queue_llm_chat
from app.services.sing import download, play, sing


def test_queue_llm_chat_routes_to_default(monkeypatch) -> None:
    apply_async = MagicMock(return_value=SimpleNamespace(id="celery-llm-1"))
    monkeypatch.setattr("app.services.llm_queue.llm_chat_task.apply_async", apply_async)
    monkeypatch.setattr("app.services.llm_queue.record_ai_llm_task_state", lambda *_args, **_kwargs: None)

    import asyncio

    task_id = asyncio.run(queue_llm_chat("req-1", "session-1", "hello", "system"))

    assert task_id == "celery-llm-1"
    _, kwargs = apply_async.call_args
    assert kwargs["queue"] == "default"


def test_sing_routes_to_media_queue(monkeypatch) -> None:
    apply_async = MagicMock(return_value=SimpleNamespace(id="celery-sing-1"))
    monkeypatch.setattr("app.services.sing.ensure_sing_worker", lambda: None)
    monkeypatch.setattr("app.services.sing.sing_task.apply_async", apply_async)

    import asyncio

    task_id = asyncio.run(sing("req-1", "amiya", 123, 0, 0, 30))

    assert task_id == "celery-sing-1"
    _, kwargs = apply_async.call_args
    assert kwargs["queue"] == "media"


def test_play_routes_to_media_queue(monkeypatch) -> None:
    apply_async = MagicMock(return_value=SimpleNamespace(id="celery-play-1"))
    monkeypatch.setattr("app.services.sing.ensure_sing_worker", lambda: None)
    monkeypatch.setattr("app.services.sing.play_task.apply_async", apply_async)
    monkeypatch.setattr("app.services.sing.ULID", lambda: "req-play-1")

    import asyncio

    request_id = asyncio.run(play("amiya"))

    assert request_id == "req-play-1"
    _, kwargs = apply_async.call_args
    assert kwargs["queue"] == "media"


def test_download_routes_to_media_queue(monkeypatch) -> None:
    apply_async = MagicMock(return_value=SimpleNamespace(id="celery-request-1"))
    monkeypatch.setattr("app.services.sing.ensure_sing_worker", lambda: None)
    monkeypatch.setattr("app.services.sing.request_task.apply_async", apply_async)

    import asyncio

    task_id = asyncio.run(download("req-2", 456))

    assert task_id == "celery-request-1"
    _, kwargs = apply_async.call_args
    assert kwargs["queue"] == "media"
