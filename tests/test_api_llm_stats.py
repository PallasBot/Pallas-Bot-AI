from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.services.llm_task_metrics import clear_llm_task_metrics_for_tests


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(enabled_endpoints={"llm_stats"}))


@pytest.fixture(autouse=True)
def reset_llm_task_metrics() -> None:
    clear_llm_task_metrics_for_tests()
    yield
    clear_llm_task_metrics_for_tests()


def test_llm_stats_endpoint_exposes_state_counts(client: TestClient) -> None:
    with (
        patch(
            "app.api.endpoints.llm_stats.llm_task_metrics_snapshot",
            return_value={
                "source": "ai",
                "day_key": "2026-06-18",
                "updated_at": 1.0,
                "by_task": {
                    "llm_chat": {
                        "queued": 1,
                        "running": 1,
                        "task_ok": 1,
                        "task_fail": 0,
                        "route_counts": {"plain_llm_chat": 1},
                    },
                    "repeater_fallback": {"task_ok": 0, "task_fail": 1},
                },
                "totals": {"task_ok": 1, "task_fail": 1},
                "state_counts": {"queued": 1, "running": 1, "succeeded": 1, "failed": 1},
                "failure_counts": {"provider_error": 1},
                "provider_stats": {
                    "openai": {
                        "requests": 1,
                        "succeeded": 1,
                        "failed": 0,
                        "avg_latency_ms": 120,
                        "recent_failure_class": None,
                    }
                },
                "model_stats": {
                    "gpt-4.1-mini": {
                        "requests": 1,
                        "succeeded": 1,
                        "failed": 0,
                        "avg_latency_ms": 120,
                        "recent_failure_class": None,
                    }
                },
            },
        ),
        patch(
            "app.api.endpoints.llm_stats.llm_token_metrics_snapshot",
            return_value={
                "source": "ai",
                "day_key": "2026-06-18",
                "updated_at": 1.0,
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "by_task": {"llm_chat": {"prompt_tokens": 100, "completion_tokens": 20}},
                "by_provider": {
                    "openai": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                    }
                },
                "by_model": {
                    "gpt-4.1-mini": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                    }
                },
            },
        ),
    ):
        response = client.get("/api/llm/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["state_counts"] == {
        "queued": 1,
        "running": 1,
        "succeeded": 1,
        "failed": 1,
    }
    assert body["failure_counts"] == {"provider_error": 1}
    assert body["provider_stats"]["openai"]["avg_latency_ms"] == 120
    assert body["model_stats"]["gpt-4.1-mini"]["requests"] == 1
    assert body["by_task"]["llm_chat"]["route_counts"] == {"plain_llm_chat": 1}
    assert body["tokens"]["by_provider"]["openai"]["total_tokens"] == 120
    assert body["tokens"]["by_model"]["gpt-4.1-mini"]["completion_tokens"] == 20
