from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.api.endpoints.chat import router as chat_router
from app.app_factory import create_app
from app.services.chat import chat


def test_legacy_chat_endpoint_enqueues_unified_llm_task(monkeypatch) -> None:
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


def test_legacy_chat_service_enqueues_unified_llm_task(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_submit(request_id: str, request) -> str:
        captured["request_id"] = request_id
        captured["session_id"] = request.session_id
        captured["system"] = request.system
        captured["messages"] = [(item.role, item.content) for item in request.messages]
        captured["metadata"] = dict(request.metadata)
        return "task-unified"

    monkeypatch.setattr("app.services.chat.submit_llm_chat_completion", fake_submit)

    task_id = asyncio.run(chat("req-disabled", "s1", "hi", 50, False))

    assert task_id == "task-unified"
    assert captured["request_id"] == "req-disabled"
    assert captured["session_id"] == "s1"
    assert captured["system"] == "你是牛牛。"
    assert captured["messages"] == [("user", "hi")]
    assert captured["metadata"] == {"task": "drunk", "token_count": 50, "tts": False, "mode": "drunk"}
