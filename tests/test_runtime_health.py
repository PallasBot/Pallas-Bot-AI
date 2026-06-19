from __future__ import annotations

from app.core.config import Settings
from app.media_task_runtime import media_task_runtime_status
from app.media_task_store import MediaTaskRecord, clear_media_task_store, store_task_record
from app.providers.router import llm_health_snapshot
from app.runtime_health import aggregate_llm_runtime_health, aggregate_media_task_runtime_health


def test_aggregate_llm_runtime_health_degraded_on_config_error() -> None:
    summary = aggregate_llm_runtime_health(
        chat_enabled=True,
        configuration_ok=False,
        provider_status=[],
    )
    assert summary["health_state"] == "degraded"
    assert summary["circuit_state"] == "open"


def test_aggregate_media_task_runtime_health_busy_queue() -> None:
    summary = aggregate_media_task_runtime_health(
        queue_depth=10,
        active_tasks=1,
        sing_package_enabled=True,
    )
    assert summary["health_state"] == "degraded"
    assert summary["degraded_state"] == "busy"


def test_llm_health_snapshot_exposes_runtime_memory_summary_config() -> None:
    summary = llm_health_snapshot(
        Settings(
            llm_chat_enabled=True,
            llm_session_backend="memory",
            llm_session_summary_enabled=True,
            llm_session_summary_threshold=16,
            llm_session_summary_keep_messages=4,
        )
    )
    assert summary["session_backend"] == "memory"
    assert summary["session_summary"]["enabled"] is True
    assert summary["session_summary"]["threshold"] == 16
    assert summary["session_summary"]["keep_messages"] == 4


def test_media_task_runtime_status_exposes_state_counts() -> None:
    clear_media_task_store()
    store_task_record(
        MediaTaskRecord(
            task_id="task-q",
            request_id="req-q",
            capability="image.generate",
            state="queued",
            provider_id="image",
            backend_id="image-local",
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
