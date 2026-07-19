"""统一 Chat 消息组装：Bot PG 会话 vs AI 仓 Redis 会话。"""

from __future__ import annotations

from typing import Any, Literal

from app.session import get_messages, message_count

LlmSessionMode = Literal["pg", "redis"]


def is_pg_session(metadata: dict[str, Any] | None) -> bool:
    if not isinstance(metadata, dict):
        return False
    raw = metadata.get("pg_session")
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def normalize_chat_history(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in messages:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        out.append({"role": role, "content": content})
    return out


def count_history_messages(
    metadata: dict[str, Any] | None,
    session: str,
    request_messages: list[dict[str, Any]] | None,
    text: str,
) -> int:
    if is_pg_session(metadata) and request_messages is not None:
        history = normalize_chat_history(request_messages)
        if history:
            return len(history)
        return 1 if str(text or "").strip() else 0
    return message_count_safe(session)


def message_count_safe(session: str) -> int:
    return message_count(session)


def build_chat_messages(
    system_prompt: str,
    metadata: dict[str, Any] | None,
    session: str,
    text: str,
    request_messages: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, str]], LlmSessionMode]:
    if is_pg_session(metadata) and request_messages is not None:
        history = normalize_chat_history(request_messages)
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        if not history and str(text or "").strip():
            messages.append({"role": "user", "content": str(text).strip()})
        return messages, "pg"

    messages = get_messages(session, system_prompt)
    user_text = str(text or "").strip()
    if user_text:
        messages.append({"role": "user", "content": user_text})
    return messages, "redis"
