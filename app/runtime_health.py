"""统一 runtime health 聚合（/health 与 probe 共用词汇）。"""

from __future__ import annotations

from typing import Any, Literal

from app.core.celery import celery_task_package_enabled

HealthState = Literal["healthy", "degraded", "unhealthy", "unknown"]
DegradedState = Literal["normal", "degraded", "busy", "overloaded"]
CircuitState = Literal["closed", "open", "half_open"]


def aggregate_media_task_runtime_health(
    *,
    queue_depth: int,
    active_tasks: int,
    sing_package_enabled: bool,
) -> dict[str, Any]:
    if not sing_package_enabled:
        return {
            "health_state": "degraded",
            "degraded_state": "degraded",
            "circuit_state": "closed",
            "recent_failure_class": "internal_error",
        }
    if queue_depth > 8 or active_tasks > 4:
        return {
            "health_state": "degraded",
            "degraded_state": "busy",
            "circuit_state": "half_open",
            "recent_failure_class": "runtime_overloaded",
        }
    return {
        "health_state": "healthy",
        "degraded_state": "normal",
        "circuit_state": "closed",
        "recent_failure_class": None,
    }


def tts_runtime_snapshot() -> dict[str, Any]:
    enabled = celery_task_package_enabled("tts")
    return {
        "capability": "tts.synthesize",
        "health_state": "healthy" if enabled else "unknown",
        "degraded_state": "normal" if enabled else "degraded",
        "circuit_state": "closed",
        "celery_enabled": enabled,
    }
