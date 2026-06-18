from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock

import pytest

from app.media_task_store import MediaTaskRecord, clear_media_task_store, store_task_record
from app.services.media_task_callback import notify_image_media_task_result, notify_sing_media_task_failed


@pytest.fixture(autouse=True)
def reset_store() -> None:
    clear_media_task_store()
    yield
    clear_media_task_store()


def test_notify_image_media_task_result_success_posts_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("app.services.media_task_callback.send_callback", send)
    record = MediaTaskRecord(
        task_id="task-1",
        request_id="draw-1-2-3-abc",
        capability="image.generate",
        state="succeeded",
        provider_id="p",
        backend_id="b",
        submitted_at=1.0,
        finished_at=2.0,
        data={"mime_type": "image/png", "b64_data": base64.b64encode(b"png-bytes").decode()},
    )
    store_task_record(record)
    asyncio.run(notify_image_media_task_result(record))
    send.assert_awaited_once()
    url, data = send.await_args.args[:2]
    assert url.endswith("/draw-1-2-3-abc")
    assert data["status"] == "success"
    assert send.await_args.kwargs["files"]["file"] == b"png-bytes"


def test_notify_image_media_task_result_failed_posts_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("app.services.media_task_callback.send_callback", send)
    record = MediaTaskRecord(
        task_id="task-2",
        request_id="draw-1-2-3-fail",
        capability="image.generate",
        state="failed",
        provider_id="p",
        backend_id="b",
        submitted_at=1.0,
        finished_at=2.0,
    )
    asyncio.run(notify_image_media_task_result(record))
    send.assert_awaited_once()
    url, data = send.await_args.args[:2]
    assert url.endswith("/draw-1-2-3-fail")
    assert data == {"status": "failed"}


def test_notify_sing_media_task_failed_posts_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    send = AsyncMock()
    monkeypatch.setattr("app.services.media_task_callback.send_callback", send)
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
    monkeypatch.setattr("app.services.media_task_callback.send_callback", send)
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
