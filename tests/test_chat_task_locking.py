from __future__ import annotations

import asyncio

import app.tasks.chat.chat_tasks as chat_tasks


def test_legacy_chat_cpu_strategy_skips_gpu_write_lock(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    class FakeChat:
        def chat(self, session: str, text: str, token_count: int = 50) -> str:
            assert session == "sess-1"
            assert text == "你好"
            assert token_count == 50
            return "ok"

    class FailLocker:
        def acquire(self, *args, **kwargs):
            raise AssertionError("cpu strategy should not acquire gpu write lock")

    async def fake_callback(request_id: str, **kwargs):
        calls.append((request_id, kwargs))

    monkeypatch.setattr(chat_tasks.settings, "chat_strategy", "cpu fp32")
    monkeypatch.setattr(chat_tasks, "gpu_locker", FailLocker())

    def fake_get_chat() -> FakeChat:
        return FakeChat()

    monkeypatch.setattr(chat_tasks.ChatManager, "get_chat", fake_get_chat)
    monkeypatch.setattr(chat_tasks, "callback", fake_callback)

    asyncio.run(chat_tasks._chat_task_async("req-1", "sess-1", "你好", 50, False))

    assert calls == [("req-1", {"text": "ok"})]
