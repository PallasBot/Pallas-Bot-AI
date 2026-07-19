import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import sing as sing_mod
from app.services.llm_queue import queue_llm_chat


def test_queue_llm_chat_routes_to_default(monkeypatch) -> None:
    apply_async = MagicMock(return_value=SimpleNamespace(id="celery-llm-1"))
    monkeypatch.setattr("app.services.llm_queue.llm_chat_task.apply_async", apply_async)
    monkeypatch.setattr("app.services.llm_queue.record_ai_llm_task_state", lambda *_args, **_kwargs: None)

    task_id = asyncio.run(queue_llm_chat("req-1", "session-1", "hello", "system"))

    assert task_id == "celery-llm-1"
    _, kwargs = apply_async.call_args
    assert kwargs["queue"] == "default"
    # 默认带过期，worker 重启后丢弃积压旧消息
    assert kwargs["expires"] == 120.0


def test_queue_llm_chat_expires_disabled(monkeypatch) -> None:
    apply_async = MagicMock(return_value=SimpleNamespace(id="celery-llm-2"))
    monkeypatch.setattr("app.services.llm_queue.llm_chat_task.apply_async", apply_async)
    monkeypatch.setattr("app.services.llm_queue.record_ai_llm_task_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.services.llm_queue.settings.llm_chat_task_expires", 0.0)

    asyncio.run(queue_llm_chat("req-2", "session-2", "hello", "system"))

    _, kwargs = apply_async.call_args
    # 关闭过期时传 None（celery 视为永不过期，旧行为）
    assert kwargs["expires"] is None


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
