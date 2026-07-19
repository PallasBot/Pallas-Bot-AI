from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.schemas.llm_chat import LlmChatMessage


class LlmReplayRequest(BaseModel):
    request_id: str = Field(min_length=1)
    request_snapshot_id: str | None = None
    mode: str = Field(default="mock_tools", min_length=1)
    task: str | None = None
    system_prompt: str = Field(min_length=1)
    messages: list[LlmChatMessage] = Field(default_factory=list)
    agent_stage_plan: list[str] = Field(default_factory=list)
    tool_catalog: dict[str, Any] = Field(default_factory=dict)
    metadata_subset: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] | None = None


class LlmReplayResponse(BaseModel):
    request_id: str
    request_snapshot_id: str | None = None
    mode: str
    task: str
    reply: str
    trace: dict[str, Any] | None = None
    assistant_message: dict[str, Any] = Field(default_factory=dict)


_llm_chat_module = import_module("app.schemas.llm_chat")

LlmReplayRequest.model_rebuild(
    _types_namespace={
        "LlmChatMessage": _llm_chat_module.LlmChatMessage,
    }
)
