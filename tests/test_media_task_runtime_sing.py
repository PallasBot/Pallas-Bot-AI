from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.media_task_runtime import refresh_sing_task_state
from app.media_task_store import MediaTaskRecord, clear_media_task_store, get_record, store_task_record


@pytest.fixture(autouse=True)
def reset_store() -> None:
    clear_media_task_store()
    yield
    clear_media_task_store()


def test_refresh_sing_task_state_marks_failed_on_success_false(monkeypatch: pytest.MonkeyPatch) -> None:
    record = MediaTaskRecord(
        task_id="task-sing-false",
        request_id="req-sing-false",
        capability="media.sing",
        state="running",
        provider_id="p",
        backend_id="b",
        submitted_at=1.0,
        celery_task_id="celery-1",
    )
    store_task_record(record)
    async_result = MagicMock(state="SUCCESS", result=False)
    monkeypatch.setattr("app.media_task_runtime.celery_app.AsyncResult", lambda _task_id: async_result)
    refresh_sing_task_state(record)
    refreshed = get_record("task-sing-false")
    assert refreshed is not None
    assert refreshed.state == "failed"
