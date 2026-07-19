from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ProviderError(Exception):
    def __init__(self, provider: str, message: str, *, status: int = 0) -> None:
        self.provider = provider
        self.status = status
        super().__init__(message)


@dataclass
class ChatCompletionParams:
    request_id: str
    session: str
    user_text: str
    system_prompt: str
    model: str | None
    options: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
