from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LlmChatMessage(BaseModel):
    role: str
    content: str


class LlmChatCompletionRequest(BaseModel):
    session_id: str = Field(min_length=1)
    system: str = Field(min_length=1)
    messages: list[LlmChatMessage] = Field(default_factory=list)
    model: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LlmChatCompletionResponse(BaseModel):
    task_id: str
    status: str


class LlmChatTask:
    LLM_CHAT = "llm_chat"
    DRUNK = "drunk"
    REPEATER_FALLBACK = "repeater_fallback"
    REPEATER_POLISH = "repeater_polish"
    REPEATER_POLISH_LITE = "repeater_polish_lite"
    REPEATER_SELECT = "repeater_select"
    AFFECT_REFINE = "affect_refine"

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        value = str(raw or cls.LLM_CHAT).strip().lower()
        allowed = {
            cls.LLM_CHAT,
            cls.DRUNK,
            cls.REPEATER_FALLBACK,
            cls.REPEATER_POLISH,
            cls.REPEATER_POLISH_LITE,
            cls.REPEATER_SELECT,
            cls.AFFECT_REFINE,
        }
        return value if value in allowed else cls.LLM_CHAT


class LlmChatMode:
    NORMAL = "normal"
    DRUNK = "drunk"

    @classmethod
    def normalize(cls, raw: str | None) -> Literal["normal", "drunk"]:
        value = str(raw or cls.NORMAL).strip().lower()
        if value == cls.DRUNK:
            return cls.DRUNK
        return cls.NORMAL
