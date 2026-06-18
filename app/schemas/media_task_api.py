from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.image_api import (
    ImageGeneratePayload,
    ResultState,
    RuntimeCaller,
    RuntimeContext,
    RuntimeErrorBody,
    RuntimePolicy,
)

MediaCapabilityId = Literal["image.generate", "media.sing"]
TaskState = Literal["pending", "queued", "running", "succeeded", "failed", "cancelled"]


class SingTaskPayload(BaseModel):
    speaker: str = Field(min_length=1, max_length=64)
    song_id: int = Field(ge=1)
    key: int = 0
    chunk_index: int = Field(default=0, ge=0)
    sing_length: int | None = Field(default=None, ge=1)


class MediaTaskSubmitRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)
    capability: MediaCapabilityId
    caller: RuntimeCaller
    context: RuntimeContext = Field(default_factory=RuntimeContext)
    policy: RuntimePolicy = Field(default_factory=RuntimePolicy)
    payload: dict[str, Any]


class MediaTaskSubmitResponse(BaseModel):
    request_id: str
    result_state: ResultState
    capability: MediaCapabilityId
    task_id: str | None = None
    provider_id: str | None = None
    backend_id: str | None = None
    data: dict[str, Any] | None = None
    error: RuntimeErrorBody | None = None


class MediaTaskStatus(BaseModel):
    task_id: str
    request_id: str
    capability: MediaCapabilityId
    state: TaskState
    provider_id: str
    backend_id: str
    submitted_at: float
    started_at: float | None = None
    finished_at: float | None = None
    queue_wait_ms: int | None = None
    task_runtime_ms: int | None = None
    failure_class: str | None = None
    error: RuntimeErrorBody | None = None
    data: dict[str, Any] | None = None


class MediaTaskCapabilityRuntime(BaseModel):
    capability: MediaCapabilityId
    queue_depth: int = 0
    active_tasks: int = 0
    health_state: Literal["healthy", "degraded", "unhealthy", "unknown"] = "unknown"


class MediaTaskRuntimeStatus(BaseModel):
    queue_depth: int = 0
    active_tasks: int = 0
    total_tasks: int = 0
    health_state: Literal["healthy", "degraded", "unhealthy", "unknown"] = "unknown"
    degraded_state: Literal["normal", "degraded", "busy", "overloaded"] = "normal"
    circuit_state: Literal["closed", "open", "half_open"] = "closed"
    recent_failure_class: str | None = None
    capabilities: list[MediaTaskCapabilityRuntime] = Field(default_factory=list)


def parse_media_task_payload(
    capability: MediaCapabilityId,
    payload: dict[str, Any],
) -> ImageGeneratePayload | SingTaskPayload:
    if capability == "image.generate":
        return ImageGeneratePayload.model_validate(payload)
    return SingTaskPayload.model_validate(payload)
