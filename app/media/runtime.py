from __future__ import annotations

import asyncio
import time
from typing import Any

from ulid import ULID

from app.core.celery import (
    celery_app,
    celery_task_package_enabled,
    require_celery_task_package,
    resolve_celery_queue_for_task,
)
from app.core.config import settings
from app.core.logger import logger
from app.media.health import aggregate_media_task_runtime_health
from app.media.services.media_task_callback import notify_sing_media_task_failed
from app.media.store import (
    MediaTaskRecord,
    clear_media_task_store,
    get_record,
    list_task_records,
    store_task_record,
    update_task_record,
)
from app.schemas.media_task_api import (
    MediaCapabilityId,
    MediaTaskCapabilityRuntime,
    MediaTaskRuntimeStatus,
    MediaTaskStatus,
    MediaTaskSubmitRequest,
    MediaTaskSubmitResponse,
    SingTaskPayload,
    parse_media_task_payload,
)
from app.schemas.runtime_api import RuntimeErrorBody

_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def clear_media_task_runtime() -> None:
    clear_media_task_store()


def media_task_runtime_status() -> MediaTaskRuntimeStatus:
    records = list_task_records()
    queue_states = {"pending", "queued"}
    active_states = {"running"}
    state_counts: dict[str, int] = {}
    by_capability: dict[str, dict[str, int]] = {}
    for record in records:
        state_counts[record.state] = state_counts.get(record.state, 0) + 1
        bucket = by_capability.setdefault(
            record.capability,
            {"queue_depth": 0, "active_tasks": 0},
        )
        if record.state in queue_states:
            bucket["queue_depth"] += 1
        if record.state in active_states:
            bucket["active_tasks"] += 1
    capabilities: list[MediaTaskCapabilityRuntime] = []
    sing_enabled = celery_task_package_enabled("sing")
    for capability, stats in sorted(by_capability.items()):
        cap_health = "healthy"
        if capability == "media.sing" and not sing_enabled:
            cap_health = "degraded"
        elif stats["queue_depth"] > 5 or stats["active_tasks"] > 3:
            cap_health = "degraded"
        capabilities.append(
            MediaTaskCapabilityRuntime(
                capability=capability,  # type: ignore[arg-type]
                queue_depth=stats["queue_depth"],
                active_tasks=stats["active_tasks"],
                health_state=cap_health,
            )
        )
    queue_depth = sum(item.queue_depth for item in capabilities)
    active_tasks = sum(item.active_tasks for item in capabilities)
    runtime_health = aggregate_media_task_runtime_health(
        queue_depth=queue_depth,
        active_tasks=active_tasks,
        sing_package_enabled=celery_task_package_enabled("sing"),
    )
    return MediaTaskRuntimeStatus(
        queue_depth=queue_depth,
        active_tasks=active_tasks,
        total_tasks=len(records),
        state_counts=state_counts,
        capabilities=capabilities,
        health_state=runtime_health["health_state"],
        degraded_state=runtime_health["degraded_state"],
        circuit_state=runtime_health["circuit_state"],
        recent_failure_class=runtime_health["recent_failure_class"],
    )


def get_media_task(task_id: str) -> MediaTaskStatus | None:
    record = get_record(task_id)
    if record is None:
        return None
    refresh_sing_task_state(record)
    refreshed = get_record(task_id)
    if refreshed is None:
        return None
    return task_status_from_record(refreshed)


def submit_media_task(body: MediaTaskSubmitRequest) -> MediaTaskSubmitResponse:
    try:
        parse_media_task_payload(body.capability, body.payload)
    except Exception as exc:
        return MediaTaskSubmitResponse(
            request_id=body.request_id,
            result_state="failed",
            capability=body.capability,
            error=RuntimeErrorBody(
                code="invalid_payload",
                message=str(exc)[:512] or "invalid task payload",
                retryable=False,
                failure_class="invalid_upstream_response",
            ),
        )

    provider_id, backend_id = provider_backend_for_capability(body.capability)

    task_id = str(ULID())
    now = time.time()
    record = MediaTaskRecord(
        task_id=task_id,
        request_id=body.request_id,
        capability=body.capability,
        state="queued",
        provider_id=provider_id,
        backend_id=backend_id,
        submitted_at=now,
        payload=dict(body.payload),
    )
    store_task_record(record)

    try:
        dispatch_sing_task(record, body)
    except Exception as exc:
        mark_task_failed(
            record,
            code="task_dispatch_failed",
            message=str(exc)[:512] or "task dispatch failed",
            failure_class="internal_error",
            retryable=False,
            notify_bot=True,
        )
        return failed_submit_response(record)

    refreshed = get_record(task_id)
    if refreshed is None:
        return MediaTaskSubmitResponse(
            request_id=body.request_id,
            result_state="failed",
            capability=body.capability,
            error=RuntimeErrorBody(
                code="task_missing",
                message="task record missing after dispatch",
                retryable=False,
                failure_class="internal_error",
            ),
        )
    return MediaTaskSubmitResponse(
        request_id=body.request_id,
        result_state="accepted",
        capability=body.capability,
        task_id=refreshed.task_id,
        provider_id=refreshed.provider_id,
        backend_id=refreshed.backend_id,
        data={"state": refreshed.state},
    )


def provider_backend_for_capability(
    capability: MediaCapabilityId,
) -> tuple[str, str]:
    if capability == "media.sing":
        return "sing-worker", "sing-local"
    msg = f"unsupported capability: {capability}"
    raise ValueError(msg)


def mark_task_running(record: MediaTaskRecord) -> None:
    now = time.time()
    update_task_record(
        record.task_id,
        state="running",
        started_at=record.started_at or now,
    )


def mark_task_failed(
    record: MediaTaskRecord,
    *,
    code: str,
    message: str,
    failure_class: str,
    retryable: bool,
    notify_bot: bool = False,
) -> None:
    now = time.time()
    error = RuntimeErrorBody(
        code=code,
        message=message,
        retryable=retryable,
        failure_class=failure_class,  # type: ignore[arg-type]
    )
    update_task_record(
        record.task_id,
        state="failed",
        finished_at=now,
        failure_class=failure_class,
        error=error,
    )
    if not notify_bot:
        return
    refreshed = get_record(record.task_id)
    if refreshed is not None and refreshed.capability == "media.sing":
        schedule_sing_failure_callback(refreshed)


def schedule_sing_failure_callback(record: MediaTaskRecord) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(notify_sing_media_task_failed(record))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def mark_task_succeeded(record: MediaTaskRecord, *, data: dict[str, Any] | None = None) -> None:
    now = time.time()
    update_task_record(
        record.task_id,
        state="succeeded",
        finished_at=now,
        data=data,
        error=None,
        failure_class=None,
    )


def failed_submit_response(record: MediaTaskRecord) -> MediaTaskSubmitResponse:
    refreshed = get_record(record.task_id)
    error = (
        refreshed.error
        if refreshed and refreshed.error
        else RuntimeErrorBody(
            code="task_failed",
            message="task failed",
            retryable=False,
            failure_class="task_failed",
        )
    )
    return MediaTaskSubmitResponse(
        request_id=record.request_id,
        result_state="failed",
        capability=record.capability,
        task_id=record.task_id,
        provider_id=record.provider_id,
        backend_id=record.backend_id,
        error=error,
    )


def task_status_from_record(record: MediaTaskRecord) -> MediaTaskStatus:
    queue_wait_ms = None
    task_runtime_ms = None
    if record.started_at is not None:
        queue_wait_ms = int(max(0.0, (record.started_at - record.submitted_at) * 1000))
    if record.started_at is not None and record.finished_at is not None:
        task_runtime_ms = int(max(0.0, (record.finished_at - record.started_at) * 1000))
    return MediaTaskStatus(
        task_id=record.task_id,
        request_id=record.request_id,
        capability=record.capability,
        state=record.state,  # type: ignore[arg-type]
        provider_id=record.provider_id,
        backend_id=record.backend_id,
        submitted_at=record.submitted_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        queue_wait_ms=queue_wait_ms,
        task_runtime_ms=task_runtime_ms,
        failure_class=record.failure_class,
        error=record.error,
        data=record.data,
    )


def dispatch_sing_task(record: MediaTaskRecord, body: MediaTaskSubmitRequest) -> None:
    from app.workers.sing import sing_task  # noqa: PLC0415 — 避免 API 启动强依赖 sing 可选包

    require_celery_task_package("sing")
    parsed = parse_media_task_payload("media.sing", body.payload)
    assert isinstance(parsed, SingTaskPayload)
    length = parsed.sing_length if parsed.sing_length and parsed.sing_length > 0 else settings.sing_length
    celery_result = sing_task.apply_async(
        args=(
            body.request_id,
            parsed.speaker,
            parsed.song_id,
            length,
            parsed.chunk_index,
            parsed.key,
        ),
        queue=resolve_celery_queue_for_task("sing"),
    )
    update_task_record(record.task_id, celery_task_id=str(celery_result.id))
    logger.info("media task {} queued sing celery={}", record.task_id, celery_result.id)


def refresh_sing_task_state(record: MediaTaskRecord) -> None:
    if record.capability != "media.sing" or record.state in {"succeeded", "failed", "cancelled"}:
        return
    if not record.celery_task_id:
        return
    async_result = celery_app.AsyncResult(record.celery_task_id)
    state = str(async_result.state or "").upper()
    if state in {"PENDING", "RECEIVED"}:
        update_task_record(record.task_id, state="queued")
        return
    if state in {"STARTED", "RETRY"}:
        mark_task_running(record)
        return
    if state == "SUCCESS":
        result_ok = True
        try:
            result_ok = bool(async_result.result)
        except Exception:
            result_ok = True
        if not result_ok:
            mark_task_failed(
                record,
                code="sing_task_failed",
                message="sing task failed",
                failure_class="task_failed",
                retryable=False,
            )
            return
        mark_task_succeeded(record, data={"celery_task_id": record.celery_task_id})
        return
    if state in {"FAILURE", "REVOKED"}:
        message = "sing task failed"
        if state == "FAILURE":
            try:
                message = str(async_result.result)[:512]
            except Exception:
                message = "sing task failed"
        mark_task_failed(
            record,
            code="sing_task_failed",
            message=message,
            failure_class="task_failed",
            retryable=False,
            notify_bot=True,
        )
