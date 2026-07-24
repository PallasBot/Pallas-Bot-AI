from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.endpoints.chat import router as chat_router
from app.app_factory import create_app
from app.services.chat import chat


def test_legacy_chat_endpoint_enqueues_chat_task(monkeypatch) -> None:
    app = create_app(enabled_endpoints=[])
    app.include_router(chat_router, prefix="/api")
    client = TestClient(app)

    captured: dict[str, object] = {}

    async def fake_chat(request_id: str, session: str, text: str, token_count: int, tts: bool) -> str:
        captured["request_id"] = request_id
        captured["session"] = session
        captured["text"] = text
        captured["token_count"] = token_count
        captured["tts"] = tts
        return "task-123"

    monkeypatch.setattr("app.api.endpoints.chat.chat", fake_chat)

    response = client.post(
        "/api/chat/req-disabled",
        json={"session": "s1", "text": "hi", "token_count": 50, "tts": False},
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-123", "status": "processing"}
    assert captured == {
        "request_id": "req-disabled",
        "session": "s1",
        "text": "hi",
        "token_count": 50,
        "tts": False,
    }


def test_legacy_chat_service_enqueues_celery_chat_task(monkeypatch) -> None:
    apply_async = MagicMock(return_value=SimpleNamespace(id="task-chat-1"))
    monkeypatch.setattr("app.services.chat.chat_task.apply_async", apply_async)
    monkeypatch.setattr("app.services.chat.require_celery_task_package", lambda _alias: None)

    task_id = asyncio.run(chat("req-disabled", "s1", "hi", 50, False))

    assert task_id == "task-chat-1"
    _, kwargs = apply_async.call_args
    assert kwargs["args"] == ["req-disabled", "s1", "hi", 50, False]
    assert kwargs["queue"] == "media"
