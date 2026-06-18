from __future__ import annotations

import pytest

from app.providers.token_usage import usage_from_local_chat_response, usage_from_remote_chat_response
from app.services.llm_token_metrics import (
    clear_llm_token_metrics_for_tests,
    llm_token_metrics_snapshot,
    record_llm_token_usage,
)


def test_record_llm_token_usage() -> None:
    clear_llm_token_metrics_for_tests()
    record_llm_token_usage(task="llm_chat", prompt_tokens=100, completion_tokens=20)
    snap = llm_token_metrics_snapshot()
    assert snap["prompt_tokens"] == 100
    assert snap["completion_tokens"] == 20
    assert snap["by_task"]["llm_chat"]["prompt_tokens"] == 100


@pytest.mark.parametrize(
    ("data", "prompt", "completion"),
    [
        ({"prompt_eval_count": 12, "eval_count": 3}, 12, 3),
        ({"usage": {"prompt_tokens": 5, "completion_tokens": 2}}, 5, 2),
    ],
)
def test_usage_parsers(data: dict, prompt: int, completion: int) -> None:
    if "usage" in data:
        assert usage_from_remote_chat_response(data) == (prompt, completion)
    else:
        assert usage_from_local_chat_response(data) == (prompt, completion)
