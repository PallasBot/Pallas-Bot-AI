from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.image_runtime import clear_image_runtime_state, image_runtime_status
from app.media_task_runtime import clear_media_task_runtime, run_image_task
from app.media_task_store import MediaTaskRecord, get_record, store_task_record
from app.schemas.media_task_api import MediaTaskSubmitRequest


@pytest.fixture(autouse=True)
def reset_media_task_runtime() -> None:
    clear_media_task_runtime()
    yield
    clear_media_task_runtime()


def _image_task_body() -> MediaTaskSubmitRequest:
    return MediaTaskSubmitRequest(
        request_id="req-callback-ok",
        capability="image.generate",
        caller={"source": "bot", "bot_id": 1, "plugin": "draw"},
        payload={"prompt": "测试", "reference_urls": []},
    )


def _store_image_record(task_id: str, request_id: str) -> None:
    store_task_record(
        MediaTaskRecord(
            task_id=task_id,
            request_id=request_id,
            capability="image.generate",
            state="queued",
            provider_id="test-provider",
            backend_id="test-backend",
            submitted_at=time.time(),
            payload={"prompt": "测试", "reference_urls": []},
        ),
    )


def test_run_image_task_callbacks_bot_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    notify = AsyncMock()
    monkeypatch.setattr("app.media_task_runtime.notify_image_media_task_result", notify)
    monkeypatch.setattr(settings, "image_enabled", True)
    monkeypatch.setattr(settings, "image_base_url", "https://image.example.com/v1")
    monkeypatch.setattr(settings, "image_api_key", "test-key")
    monkeypatch.setattr(
        "app.media_task_runtime.submit_image_generate",
        AsyncMock(
            return_value=MagicMock(
                result_state="success",
                data=MagicMock(mime_type="image/png", b64_data="aGVsbG8="),
                latency_ms=12,
                error=None,
            ),
        ),
    )
    clear_image_runtime_state()
    task_id = "task-callback-ok"
    body = _image_task_body()
    _store_image_record(task_id, body.request_id)
    asyncio.run(run_image_task(task_id, body))
    notify.assert_awaited_once()
    record = get_record(task_id)
    assert record is not None
    assert record.state == "succeeded"
    assert image_runtime_status().health_state == "healthy"


def test_run_image_task_callbacks_bot_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    notify = AsyncMock()
    monkeypatch.setattr("app.media_task_runtime.notify_image_media_task_result", notify)
    monkeypatch.setattr(
        "app.media_task_runtime.submit_image_generate",
        AsyncMock(
            return_value=MagicMock(
                result_state="failed",
                data=None,
                latency_ms=None,
                error=MagicMock(
                    code="image_task_failed",
                    message="boom",
                    retryable=False,
                    failure_class="task_failed",
                ),
            ),
        ),
    )
    task_id = "task-callback-fail"
    body = MediaTaskSubmitRequest(
        request_id="req-callback-fail",
        capability="image.generate",
        caller={"source": "bot", "bot_id": 1, "plugin": "draw"},
        payload={"prompt": "测试", "reference_urls": []},
    )
    _store_image_record(task_id, body.request_id)
    asyncio.run(run_image_task(task_id, body))
    notify.assert_awaited_once()
    record = get_record(task_id)
    assert record is not None
    assert record.state == "failed"
