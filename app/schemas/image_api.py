from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CapabilityId = Literal["image.generate"]
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


class ImageGatewayBackend(BaseModel):
    """Bot 下发的单条画图上游（主网关或备线）。"""

    base_url: str = Field(default="", max_length=2_048)
    api_key: str = Field(default="", max_length=2_048)
    model: str = Field(default="", max_length=256)
    omit_response_format: bool = False
    name: str = Field(default="", max_length=128)


class ImageGatewaySpec(BaseModel):
    backends: list[ImageGatewayBackend] = Field(default_factory=list, max_length=16)


class ImageGeneratePayload(BaseModel):
    prompt: str = Field(min_length=1, max_length=8_000)
    reference_urls: list[str] = Field(default_factory=list, max_length=8)
    gateway: ImageGatewaySpec | None = None


class ImageGenerateRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    capability: CapabilityId = "image.generate"
    caller: RuntimeCaller
    context: RuntimeContext = Field(default_factory=RuntimeContext)
    policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    payload: ImageGeneratePayload


class ImageArtifact(BaseModel):
    mime_type: str = Field(default="image/png", min_length=1, max_length=64)
    b64_data: str = Field(min_length=1)


class ImageGenerateResponse(BaseModel):
    request_id: str
    result_state: ResultState
    capability: CapabilityId = "image.generate"
    task_id: str | None = None
    provider_id: str | None = None
    backend_id: str | None = None
    latency_ms: int | None = None
    data: ImageArtifact | None = None
    error: RuntimeErrorBody | None = None


class ImageBackendStatus(BaseModel):
    backend_id: str
    provider_id: str
    health_state: HealthState = "unknown"
    circuit_state: CircuitState = "closed"
    last_latency_ms: int | None = None
    consecutive_failures: int = 0
    recent_failure_class: FailureClass | None = None


class ImageRuntimeStatus(BaseModel):
    capability: CapabilityId = "image.generate"
    health_state: HealthState = "unknown"
    degraded_state: DegradedState = "normal"
    queue_depth: int = 0
    active_requests: int = 0
    active_tasks: int = 0
    recent_success_rate: float | None = None
    backends: list[ImageBackendStatus] = Field(default_factory=list)
