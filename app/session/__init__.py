from __future__ import annotations

from typing import Any, Protocol

from app.core.config import settings

from . import memory, redis_store


class SessionStore(Protocol):
    def get_messages(self, session: str, system_prompt: str) -> list[dict[str, str]]: ...

    def save_messages(self, session: str, messages: list[dict[str, Any]]) -> None: ...

    def reset_session(self, session: str, system_prompt: str) -> None: ...

    def del_session(self, session: str) -> None: ...

    def message_count(self, session: str) -> int: ...


class MemorySessionStore:
    def get_messages(self, session: str, system_prompt: str) -> list[dict[str, str]]:
        return memory.get_messages(session, system_prompt)

    def save_messages(self, session: str, messages: list[dict[str, Any]]) -> None:
        memory.save_messages(session, messages)

    def reset_session(self, session: str, system_prompt: str) -> None:
        memory.reset_session(session, system_prompt)

    def del_session(self, session: str) -> None:
        memory.del_session(session)

    def message_count(self, session: str) -> int:
        return memory.message_count(session)


class RedisSessionStore:
    def get_messages(self, session: str, system_prompt: str) -> list[dict[str, str]]:
        return redis_store.get_messages(session, system_prompt)

    def save_messages(self, session: str, messages: list[dict[str, Any]]) -> None:
        redis_store.save_messages(session, messages)

    def reset_session(self, session: str, system_prompt: str) -> None:
        redis_store.reset_session(session, system_prompt)

    def del_session(self, session: str) -> None:
        redis_store.del_session(session)

    def message_count(self, session: str) -> int:
        return redis_store.message_count(session)


def normalize_session_backend(raw: str | None) -> str:
    value = str(raw or "redis").strip().lower()
    if value in ("memory", "local"):
        return "memory"
    return "redis"


def get_session_store() -> SessionStore:
    backend = normalize_session_backend(settings.llm_session_backend)
    if backend == "redis":
        return RedisSessionStore()
    return MemorySessionStore()


def get_messages(session: str, system_prompt: str) -> list[dict[str, str]]:
    return get_session_store().get_messages(session, system_prompt)


def save_messages(session: str, messages: list[dict[str, Any]]) -> None:
    get_session_store().save_messages(session, messages)


def reset_session(session: str, system_prompt: str) -> None:
    get_session_store().reset_session(session, system_prompt)


def del_session(session: str) -> None:
    get_session_store().del_session(session)


def message_count(session: str) -> int:
    return get_session_store().message_count(session)
