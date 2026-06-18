from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Literal

from app.core.config import settings
from app.schemas.image_api import RuntimeErrorBody
from app.session.redis_store import ping_redis_sync, redis_client

MediaCapabilityId = Literal["image.generate", "media.sing"]

_TASK_LOCK = Lock()
_MEMORY_TASKS: dict[str, MediaTaskRecord] = {}
_MAX_MEMORY_TASKS = 500
_KEY_PREFIX = "media:task:"
_DEFAULT_TTL_SEC = 86_400


@dataclass
class MediaTaskRecord:
    task_id: str
    request_id: str
    capability: MediaCapabilityId
    state: str
    provider_id: str
    backend_id: str
    submitted_at: float
    started_at: float | None = None
    finished_at: float | None = None
    failure_class: str | None = None
    error: RuntimeErrorBody | None = None
    data: dict[str, Any] | None = None
    celery_task_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    bot_callback_notified: bool = False


def media_task_ttl_sec() -> int:
    raw = int(getattr(settings, "media_task_ttl_sec", _DEFAULT_TTL_SEC) or _DEFAULT_TTL_SEC)
    return max(300, min(raw, 7 * 86_400))


def redis_task_store_enabled() -> bool:
    return ping_redis_sync()


def clear_media_task_store() -> None:
    with _TASK_LOCK:
        _MEMORY_TASKS.clear()


def store_task_record(record: MediaTaskRecord) -> None:
    with _TASK_LOCK:
        if len(_MEMORY_TASKS) >= _MAX_MEMORY_TASKS:
            oldest_id = min(_MEMORY_TASKS.values(), key=lambda item: item.submitted_at).task_id
            _MEMORY_TASKS.pop(oldest_id, None)
        _MEMORY_TASKS[record.task_id] = record
    persist_task_record(record)


def get_record(task_id: str) -> MediaTaskRecord | None:
    with _TASK_LOCK:
        record = _MEMORY_TASKS.get(task_id)
    if record is not None:
        return record
    loaded = load_task_record_from_redis(task_id)
    if loaded is None:
        return None
    with _TASK_LOCK:
        _MEMORY_TASKS[task_id] = loaded
    return loaded


def update_task_record(task_id: str, **changes: Any) -> MediaTaskRecord | None:
    record = get_record(task_id)
    if record is None:
        return None
    for key, value in changes.items():
        setattr(record, key, value)
    store_task_record(record)
    return record


def list_task_records() -> list[MediaTaskRecord]:
    with _TASK_LOCK:
        return list(_MEMORY_TASKS.values())


def task_key(task_id: str) -> str:
    return f"{_KEY_PREFIX}{task_id}"


def record_to_dict(record: MediaTaskRecord) -> dict[str, Any]:
    return {
        "task_id": record.task_id,
        "request_id": record.request_id,
        "capability": record.capability,
        "state": record.state,
        "provider_id": record.provider_id,
        "backend_id": record.backend_id,
        "submitted_at": record.submitted_at,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "failure_class": record.failure_class,
        "error": record.error.model_dump() if record.error is not None else None,
        "data": record.data,
        "celery_task_id": record.celery_task_id,
        "payload": record.payload,
        "bot_callback_notified": record.bot_callback_notified,
    }


def record_from_dict(data: dict[str, Any]) -> MediaTaskRecord | None:
    task_id = str(data.get("task_id") or "").strip()
    if not task_id:
        return None
    error_raw = data.get("error")
    error = RuntimeErrorBody.model_validate(error_raw) if isinstance(error_raw, dict) else None
    capability = str(data.get("capability") or "").strip()
    if capability not in {"image.generate", "media.sing"}:
        return None
    return MediaTaskRecord(
        task_id=task_id,
        request_id=str(data.get("request_id") or ""),
        capability=capability,  # type: ignore[arg-type]
        state=str(data.get("state") or "queued"),
        provider_id=str(data.get("provider_id") or ""),
        backend_id=str(data.get("backend_id") or ""),
        submitted_at=float(data.get("submitted_at") or time.time()),
        started_at=float(data["started_at"]) if data.get("started_at") is not None else None,
        finished_at=float(data["finished_at"]) if data.get("finished_at") is not None else None,
        failure_class=str(data["failure_class"]) if data.get("failure_class") else None,
        error=error,
        data=data.get("data") if isinstance(data.get("data"), dict) else None,
        celery_task_id=str(data["celery_task_id"]) if data.get("celery_task_id") else None,
        payload=data.get("payload") if isinstance(data.get("payload"), dict) else {},
        bot_callback_notified=bool(data.get("bot_callback_notified")),
    )


def persist_task_record(record: MediaTaskRecord) -> None:
    if not redis_task_store_enabled():
        return
    try:
        payload = json.dumps(record_to_dict(record), ensure_ascii=False)
        redis_client().setex(task_key(record.task_id), media_task_ttl_sec(), payload)
    except Exception:
        return


def load_task_record_from_redis(task_id: str) -> MediaTaskRecord | None:
    if not redis_task_store_enabled():
        return None
    try:
        raw = redis_client().get(task_key(task_id))
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return record_from_dict(data)
    except Exception:
        return None
