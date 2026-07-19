from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_legacy_chat_passes_metadata_to_submit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_chat_enabled", True)
    captured: dict = {}

    async def fake_submit(request_id: str, request):
        captured["request_id"] = request_id
        captured["request"] = request
        return "task-legacy-1"

    with patch("app.api.endpoints.llm_manage.submit_llm_chat_completion", new=AsyncMock(side_effect=fake_submit)):
        response = client.post(
            "/api/llm/chat/req-legacy-1",
            json={
                "session": "sess-1",
                "text": "你好",
                "system_prompt": "sys",
                "metadata": {"task": "repeater_polish", "temperature": 0.4, "token_count": 80},
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "task-legacy-1"
    req = captured["request"]
    assert req.metadata["task"] == "repeater_polish"
    assert req.metadata["temperature"] == 0.4
    assert req.metadata["token_count"] == 80
