from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import redis

from app.core.config import settings

_KEY_PREFIX = "llm:session:"


@lru_cache
def redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def ping_redis_sync() -> bool:
    try:
        return bool(redis_client().ping())
    except redis.RedisError:
        return False


def session_key(session: str) -> str:
    return f"{_KEY_PREFIX}{session}"


def load_messages(session: str) -> list[dict[str, str]] | None:
    raw = redis_client().get(session_key(session))
    if not raw:
        return None
    data = json.loads(raw)
    if not isinstance(data, list):
        return None
    return [item for item in data if isinstance(item, dict)]


def get_messages(session: str, system_prompt: str) -> list[dict[str, str]]:
    messages = load_messages(session)
    if messages is None:
        messages = [{"role": "system", "content": system_prompt}]
        save_messages(session, messages)
        return list(messages)
    if messages and messages[0].get("role") == "system":
        if messages[0].get("content") != system_prompt:
            messages[0] = {"role": "system", "content": system_prompt}
            save_messages(session, messages)
    elif messages:
        messages.insert(0, {"role": "system", "content": system_prompt})
        save_messages(session, messages)
    else:
        messages = [{"role": "system", "content": system_prompt}]
        save_messages(session, messages)
    return list(messages)


def save_messages(session: str, messages: list[dict[str, Any]]) -> None:
    payload = json.dumps(messages, ensure_ascii=False)
    redis_client().set(session_key(session), payload)


def reset_session(session: str, system_prompt: str) -> None:
    save_messages(session, [{"role": "system", "content": system_prompt}])


def del_session(session: str) -> None:
    redis_client().delete(session_key(session))


def message_count(session: str) -> int:
    messages = load_messages(session)
    return len(messages) if messages else 0
