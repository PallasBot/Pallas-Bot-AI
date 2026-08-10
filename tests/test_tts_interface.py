from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest

GPT_SOVITS_PACKAGE = Path(__file__).parents[1] / "app/workers/tts/GPT_SoVITS"
GPT_SOVITS_ROOT = GPT_SOVITS_PACKAGE / "GPT_SoVITS"
sys.path.insert(0, str(GPT_SOVITS_PACKAGE))
sys.path.insert(0, str(GPT_SOVITS_ROOT))

from app.workers.tts.GPT_SoVITS import interface  # noqa: E402


class FakePipeline:
    def __init__(self, generator) -> None:
        self.generator = generator

    def run(self, _req: dict):
        return self.generator()


def test_tts_handle_propagates_error_after_fallback_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduled: list[bool] = []

    def failed_generator():
        yield 16000, np.zeros(16000, dtype=np.int16)
        raise RuntimeError("Half != float")

    monkeypatch.setattr(interface._tts_pipeline_cache, "get", lambda: FakePipeline(failed_generator))
    monkeypatch.setattr(interface._tts_pipeline_cache, "schedule_unload", lambda: scheduled.append(True))

    with pytest.raises(RuntimeError, match="Half != float"):
        interface.tts_handle({"text": "测试", "media_type": "wav"})

    assert scheduled == [True]


def test_tts_handle_returns_completed_non_streaming_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    audio = np.array([1, -1], dtype=np.int16)

    def completed_generator():
        yield 32000, audio

    monkeypatch.setattr(interface._tts_pipeline_cache, "get", lambda: FakePipeline(completed_generator))
    monkeypatch.setattr(interface._tts_pipeline_cache, "schedule_unload", lambda: None)
    monkeypatch.setattr(interface, "pack_audio", lambda *_args: BytesIO(b"wav-data"))

    assert interface.tts_handle({"text": "测试", "media_type": "wav"}) == b"wav-data"
