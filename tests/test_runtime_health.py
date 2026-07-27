from __future__ import annotations

from app.media.health import aggregate_media_task_runtime_health
from app.media.runtime import media_task_runtime_status
from app.media.store import MediaTaskRecord, clear_media_task_store, store_task_record


def test_aggregate_media_task_runtime_health_busy_queue() -> None:
    summary = aggregate_media_task_runtime_health(
        queue_depth=10,
        active_tasks=1,
        sing_package_enabled=True,
    )
    assert summary["health_state"] == "degraded"
    assert summary["degraded_state"] == "busy"


def test_media_task_runtime_status_exposes_state_counts() -> None:
    clear_media_task_store()
    store_task_record(
        MediaTaskRecord(
            task_id="task-q",
            request_id="req-q",
            capability="media.sing",
            state="queued",
            provider_id="sing",
            backend_id="sing-local",
            submitted_at=1.0,
        )
    )
    store_task_record(
        MediaTaskRecord(
            task_id="task-r",
            request_id="req-r",
            capability="media.sing",
            state="running",
            provider_id="sing",
            backend_id="sing-local",
            submitted_at=2.0,
        )
    )
    store_task_record(
        MediaTaskRecord(
            task_id="task-f",
            request_id="req-f",
            capability="media.sing",
            state="failed",
            provider_id="sing",
            backend_id="sing-local",
            submitted_at=3.0,
        )
    )

    runtime = media_task_runtime_status()

    assert runtime.total_tasks == 3
    assert runtime.state_counts == {
        "queued": 1,
        "running": 1,
        "failed": 1,
    }
