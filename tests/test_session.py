from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.providers.router import llm_health_snapshot
from app.session import (
    MemorySessionStore,
    RedisSessionStore,
    normalize_session_backend,
    redis_store,
)
from app.session import memory as memory_store


def test_normalize_session_backend() -> None:
    assert normalize_session_backend("memory") == "memory"
    assert normalize_session_backend("local") == "memory"
    assert normalize_session_backend("redis") == "redis"
    assert normalize_session_backend("shared") == "redis"
    assert normalize_session_backend(None) == "redis"


def test_memory_session_roundtrip() -> None:
    memory_store.del_session("mem-1")
    store = MemorySessionStore()
    messages = store.get_messages("mem-1", "sys-a")
    messages.append({"role": "user", "content": "hi"})
    store.save_messages("mem-1", messages)
    assert store.message_count("mem-1") == 2
    loaded = store.get_messages("mem-1", "sys-a")
    assert loaded[-1]["content"] == "hi"
    store.reset_session("mem-1", "sys-b")
    assert store.message_count("mem-1") == 1
    store.del_session("mem-1")
    assert store.message_count("mem-1") == 0


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def ping(self) -> bool:
        return True


def test_redis_session_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(redis_store, "redis_client", lambda: fake)
    store = RedisSessionStore()
    messages = store.get_messages("redis-1", "sys")
    messages.append({"role": "user", "content": "hello"})
    store.save_messages("redis-1", messages)
    raw = fake.get(redis_store.session_key("redis-1"))
    assert raw is not None
    payload = json.loads(raw)
    assert payload[-1]["content"] == "hello"
    store.del_session("redis-1")
    assert fake.get(redis_store.session_key("redis-1")) is None


def test_llm_health_includes_session_backend() -> None:
    snap = llm_health_snapshot(Settings(llm_session_backend="redis"))
    assert snap["session_backend"] == "redis"


def test_llm_health_includes_session_summary_settings() -> None:
    snap = llm_health_snapshot(
        Settings(
            llm_session_backend="redis",
            llm_session_summary_enabled=True,
            llm_session_summary_threshold=18,
            llm_session_summary_keep_messages=5,
        )
    )
    assert snap["session_summary"] == {
        "enabled": True,
        "threshold": 18,
        "keep_messages": 5,
    }
