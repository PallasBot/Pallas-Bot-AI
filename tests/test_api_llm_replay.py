from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.config import settings


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(enabled_endpoints={"llm_chat"}))


def test_llm_replay_endpoint_runs_sync_replay(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_chat_enabled", True)

    async def fake_run_replay(request):
        assert request.request_id == "req-1"
        assert request.mode == "mock_tools"
        assert request.messages[0].role == "user"
        return {
            "request_id": "req-1",
            "mode": "mock_tools",
            "task": "llm_chat",
            "reply": "查到了",
            "trace": {"tool_call_count": 1},
            "assistant_message": {"role": "assistant", "content": "查到了"},
        }

    with patch("app.api.endpoints.llm_chat.run_llm_replay", new=AsyncMock(side_effect=fake_run_replay)):
        response = client.post(
            "/api/v1/chat/replay",
            json={
                "request_id": "req-1",
                "mode": "mock_tools",
                "task": "llm_chat",
                "system_prompt": "你是牛牛",
                "messages": [{"role": "user", "content": "查一下银灰"}],
                "agent_stage_plan": ["plan", "tool_loop", "generate"],
                "tool_catalog": {"version": "tool_catalog/v1", "tools": []},
                "metadata_subset": {"task": "llm_chat", "bot_id": 10001, "group_id": 20002, "user_id": 30003},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_id"] == "req-1"
    assert body["mode"] == "mock_tools"
    assert body["task"] == "llm_chat"
    assert body["reply"] == "查到了"
