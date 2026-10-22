from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.media.services import media_task_callback
from app.media.services.media_task_callback import notify_sing_media_task_failed
from app.media.store import MediaTaskRecord, clear_media_task_store


@pytest.fixture(autouse=True)
def reset_store() -> None:
    clear_media_task_store()
    yield
    clear_media_task_store()


def test_notify_sing_media_task_failed_posts_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("app.media.services.media_task_callback.send_callback", send)
    record = MediaTaskRecord(
        task_id="task-sing-fail",
        request_id="sing-req-fail",
        capability="media.sing",
        state="failed",
        provider_id="p",
        backend_id="b",
        submitted_at=1.0,
        finished_at=2.0,
    )
    asyncio.run(notify_sing_media_task_failed(record))
    send.assert_awaited_once()
    url, data = send.await_args.args[:2]
    assert url.endswith("/sing-req-fail")
    assert data == {"status": "failed"}


def test_notify_sing_media_task_failed_skips_when_notified(monkeypatch: pytest.MonkeyPatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("app.media.services.media_task_callback.send_callback", send)
    record = MediaTaskRecord(
        task_id="task-sing-skip",
        request_id="sing-req-skip",
        capability="media.sing",
        state="failed",
        provider_id="p",
        backend_id="b",
        submitted_at=1.0,
        finished_at=2.0,
        bot_callback_notified=True,
    )
    asyncio.run(notify_sing_media_task_failed(record))
    send.assert_not_awaited()


def test_notify_sing_media_task_failed_redacts_exception_message(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    async def fail(*_args, **_kwargs):
        raise RuntimeError("http://localhost/callback?Authorization=Bearer fake-secret")

    def capture_warning(message: str, *args, **_kwargs) -> None:
        messages.append(message.format(*args) if args else message)

    monkeypatch.setattr(media_task_callback, "send_callback", fail)
    monkeypatch.setattr(media_task_callback.logger, "warning", capture_warning)
    record = MediaTaskRecord(
        task_id="task-sing-error",
        request_id="sing-req-error",
        capability="media.sing",
        state="failed",
        provider_id="p",
        backend_id="b",
        submitted_at=1.0,
        finished_at=2.0,
    )

    asyncio.run(notify_sing_media_task_failed(record))

    assert messages
    assert "RuntimeError" in messages[0]
    assert "fake-secret" not in messages[0]
    assert "http://" not in messages[0]
