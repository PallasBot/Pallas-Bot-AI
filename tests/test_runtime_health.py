from __future__ import annotations

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
