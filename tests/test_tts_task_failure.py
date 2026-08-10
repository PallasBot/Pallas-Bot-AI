from __future__ import annotations

import asyncio
from contextlib import nullcontext

import pytest

from app.workers.tts import tts_tasks


def test_tts_task_callbacks_failed_without_audio_on_synthesis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks: list[tuple[str, dict]] = []

    monkeypatch.setattr(tts_tasks.gpu_locker, "acquire", lambda **_kwargs: nullcontext())
    monkeypatch.setattr(
        tts_tasks,
        "resolve_tts_request",
        lambda **_kwargs: {"text": "测试", "media_type": "wav"},
    )
    monkeypatch.setattr(tts_tasks, "translate_for_tts", lambda _text: None)
    monkeypatch.setattr(
        tts_tasks,
        "tts_handle",
        lambda _req: (_ for _ in ()).throw(RuntimeError("Half != float")),
    )

    async def capture_callback(request_id: str, **kwargs) -> None:
        callbacks.append((request_id, kwargs))

    monkeypatch.setattr(tts_tasks, "callback", capture_callback)

    asyncio.run(tts_tasks._tts_task_async("request-id", "测试"))

    assert callbacks == [("request-id", {"status": "failed"})]
