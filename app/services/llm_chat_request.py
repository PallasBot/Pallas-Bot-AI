from __future__ import annotations

from typing import Any

from app.schemas.llm_chat import LlmChatCompletionRequest


def parse_llm_chat_completion_request(body: dict[str, Any]) -> LlmChatCompletionRequest:
    capability = str(body.get("capability") or "").strip()
    payload = body.get("payload")
    if capability == "llm.chat" and isinstance(payload, dict):
        merged = dict(payload)
        context = body.get("context")
        if isinstance(context, dict):
            context_metadata = context.get("metadata")
            if isinstance(context_metadata, dict):
                metadata = dict(merged.get("metadata") or {})
                metadata.update(context_metadata)
                merged["metadata"] = metadata
            for key in ("group_id", "user_id", "session_id"):
                if key in context and context.get(key) is not None:
                    metadata = dict(merged.get("metadata") or {})
                    metadata.setdefault(key, context.get(key))
                    merged["metadata"] = metadata
        return LlmChatCompletionRequest.model_validate(merged)
    return LlmChatCompletionRequest.model_validate(body)
