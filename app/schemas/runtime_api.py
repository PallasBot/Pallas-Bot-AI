from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ResultState = Literal["success", "accepted", "failed"]
FailureClass = Literal[
    "timeout",
    "connect_error",
    "provider_unavailable",
    "unsupported_operation",
    "invalid_upstream_response",
    "runtime_overloaded",
    "rate_limited",
    "task_failed",
    "internal_error",
]
HealthState = Literal["healthy", "degraded", "unhealthy", "unknown"]
CircuitState = Literal["closed", "open", "half_open"]
DegradedState = Literal["normal", "busy", "overloaded", "degraded"]


class RuntimeCaller(BaseModel):
    source: str = Field(default="bot", min_length=1, max_length=32)
    bot_id: int
    plugin: str = Field(min_length=1, max_length=128)


class RuntimeContext(BaseModel):
    group_id: int | None = None
    user_id: int | None = None
    session_id: str | None = None
    persona_version: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimePolicy(BaseModel):
    mode: str = "default"
    timeout_sec: float | None = Field(default=None, gt=0)
    allow_fallback: bool = True
    prefer_local: bool = False
    force_task_mode: bool = False
    max_latency_ms: int | None = Field(default=None, ge=1)
    deliver_mode: Literal["poll", "callback"] = "callback"


class RuntimeErrorBody(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=512)
    retryable: bool = False
    failure_class: FailureClass
