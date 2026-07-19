from typing import Any

from pydantic import BaseModel, Field


class LlmLegacyChatRequest(BaseModel):
    session: str
    text: str
    system_prompt: str = Field(min_length=1)
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LlmTaskResponse(BaseModel):
    task_id: str
    status: str


class LlmModelResponse(BaseModel):
    model: str
    num_gpu: int | None = None


class LlmModelUpdateRequest(BaseModel):
    model: str = Field(min_length=1)
    pull: bool = True


class LlmNumGpuUpdateRequest(BaseModel):
    num_gpu: int = Field(ge=0, le=999)
