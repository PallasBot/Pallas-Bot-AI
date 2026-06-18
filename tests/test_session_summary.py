from __future__ import annotations

import asyncio

from app.services.llm_task_metrics import (
    clear_llm_task_metrics_for_tests,
    llm_task_metrics_snapshot,
    record_ai_llm_classification,
)
from app.services.session_summary import format_transcript, maybe_compact_request_messages


def test_maybe_compact_request_messages_skips_short_history(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.session_summary.session_summary_settings",
        lambda _meta: {"enabled": True, "threshold": 10, "keep_messages": 4},
    )
    messages = [{"role": "user", "content": f"msg{i}"} for i in range(6)]

    async def run():
        return await maybe_compact_request_messages(messages, metadata={})

    compacted, pending = asyncio.run(run())
    assert compacted == messages
    assert pending is None


def test_maybe_compact_request_messages_summarizes_old_rounds(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.session_summary.session_summary_settings",
        lambda _meta: {"enabled": True, "threshold": 6, "keep_messages": 2},
    )

    async def fake_summarize(messages):
        assert len(messages) == 4
        return "博士聊了银灰"

    monkeypatch.setattr("app.services.session_summary.summarize_chat_history", fake_summarize)
    messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"turn{i}"} for i in range(6)]

    async def run():
        return await maybe_compact_request_messages(messages, metadata={})

    compacted, pending = asyncio.run(run())
    assert pending is not None
    assert pending["summary"] == "博士聊了银灰"
    assert compacted is not None
    assert compacted[0]["content"].startswith("【此前对话摘要】")
    assert len(compacted) == 3


def test_format_transcript() -> None:
    text = format_transcript([
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "嗯"},
    ])
    assert "用户：你好" in text
    assert "助手：嗯" in text


def test_record_ai_llm_classification() -> None:
    clear_llm_task_metrics_for_tests()
    record_ai_llm_classification({
        "task": "llm_chat",
        "classification": {"tier": "medium", "needs_tools": True},
    })
    snap = llm_task_metrics_snapshot()
    assert snap["classification"]["totals"]["tier_medium"] == 1
    assert snap["classification"]["totals"]["tools_on"] == 1
    assert snap["classification"]["totals"]["vision_off"] == 1
