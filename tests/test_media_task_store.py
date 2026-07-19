from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.media_task_store import (
    MediaTaskRecord,
    clear_media_task_store,
    get_record,
    load_task_record_from_redis,
    persist_task_record,
    record_from_dict,
    record_to_dict,
    store_task_record,
)


def test_record_roundtrip_dict() -> None:
    record = MediaTaskRecord(
        task_id="task-1",
        request_id="req-1",
        capability="image.generate",
        state="queued",
        provider_id="image-gateway",
        backend_id="image-primary",
        submitted_at=1.0,
        payload={"prompt": "test"},
    )
    restored = record_from_dict(record_to_dict(record))
    assert restored is not None
    assert restored.task_id == "task-1"
    assert restored.capability == "image.generate"
    assert restored.payload == {"prompt": "test"}


def test_store_and_get_from_memory() -> None:
    clear_media_task_store()
    record = MediaTaskRecord(
        task_id="task-2",
        request_id="req-2",
        capability="media.sing",
        state="queued",
        provider_id="sing-worker",
        backend_id="sing-local",
        submitted_at=2.0,
    )
    store_task_record(record)
    loaded = get_record("task-2")
    assert loaded is not None
    assert loaded.request_id == "req-2"


@patch("app.media_task_store.redis_task_store_enabled", return_value=True)
@patch("app.media_task_store.redis_client")
def test_persist_and_load_from_redis(mock_redis_client: MagicMock, mock_enabled: MagicMock) -> None:
    assert mock_enabled.return_value is True
    clear_media_task_store()
    client = MagicMock()
    mock_redis_client.return_value = client
    stored: dict[str, str] = {}

    def _setex(key: str, _ttl: int, value: str) -> None:
        stored[key] = value

    client.setex.side_effect = _setex
    client.get.side_effect = stored.get

    record = MediaTaskRecord(
        task_id="task-3",
        request_id="req-3",
        capability="image.generate",
        state="succeeded",
        provider_id="image-gateway",
        backend_id="image-primary",
        submitted_at=3.0,
        data={"b64_data": "aGVsbG8="},
    )
    persist_task_record(record)
    assert client.setex.called
    payload = json.loads(stored["media:task:task-3"])
    assert payload["state"] == "succeeded"
    loaded = load_task_record_from_redis("task-3")
    assert loaded is not None
    assert loaded.data == {"b64_data": "aGVsbG8="}
