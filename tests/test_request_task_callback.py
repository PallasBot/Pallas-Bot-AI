from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest


def _install_sing_import_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub optional sing-stack deps so sing_tasks can be imported under --group dev."""
    asyncer = types.ModuleType("asyncer")
    asyncer.asyncify = lambda fn: fn
    monkeypatch.setitem(sys.modules, "asyncer", asyncer)

    for name in (
        "pydub",
        "pyncm_async",
        "pyncm_async.apis",
        "pyncm_async.apis.login",
        "librosa",
        "soundfile",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))

    pkg = "app.workers.sing"
    stubs = {
        "mixer": {"mix": lambda *args, **kwargs: None, "splice": lambda *args, **kwargs: None},
        "ncm_loader": {"download": lambda *args, **kwargs: None},
        "separater": {"separate": lambda *args, **kwargs: None},
        "slicer": {"slice_audio": lambda *args, **kwargs: None},
        "svc_inference": {"inference": lambda *args, **kwargs: None},
    }
    for sub, attrs in stubs.items():
        full = f"{pkg}.{sub}"
        stub = types.ModuleType(full)
        for name, value in attrs.items():
            setattr(stub, name, value)
        monkeypatch.setitem(sys.modules, full, stub)

    # Force a fresh import against the stubs above.
    monkeypatch.delitem(sys.modules, "app.workers.sing.sing_tasks", raising=False)
    monkeypatch.delitem(sys.modules, "app.workers.sing", raising=False)


def test_request_task_callback_includes_song_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_sing_import_stubs(monkeypatch)
    from app.workers.sing import sing_tasks

    audio_path = tmp_path / "12345.mp3"
    audio_path.write_bytes(b"fake-audio")

    captured: dict = {}

    async def fake_download(song_id: int):
        assert song_id == 12345
        return audio_path

    async def fake_callback(request_id: str, **kwargs):
        captured["request_id"] = request_id
        captured.update(kwargs)

    monkeypatch.setattr(sing_tasks, "download", fake_download)
    monkeypatch.setattr(sing_tasks, "callback", fake_callback)

    ok = asyncio.run(sing_tasks._request_task_async("req-song-1", 12345))

    assert ok is True
    assert captured["request_id"] == "req-song-1"
    assert captured["audio"] == b"fake-audio"
    assert captured["song_id"] == "12345"
    assert captured["chunk_index"] == 0
    assert captured["key"] == 0
