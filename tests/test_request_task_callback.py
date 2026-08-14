from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pytest


def _install_ncm_import_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub pyncm_async so app.media.services.ncm_loader 可在 dev 依赖下导入。"""
    for name in ("pyncm_async", "pyncm_async.apis", "pyncm_async.apis.login"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))


def test_request_task_callback_includes_song_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_ncm_import_stubs(monkeypatch)
    from app.workers.fast import request_tasks

    audio_path = tmp_path / "12345.mp3"
    audio_path.write_bytes(b"fake-audio")

    captured: dict = {}

    async def fake_download(song_id: int):
        assert song_id == 12345
        return audio_path

    async def fake_callback(request_id: str, **kwargs):
        captured["request_id"] = request_id
        captured.update(kwargs)

    monkeypatch.setattr("app.media.services.ncm_loader.download", fake_download)
    monkeypatch.setattr(request_tasks, "callback", fake_callback)

    ok = asyncio.run(request_tasks._request_task_async("req-song-1", 12345))

    assert ok is True
    assert captured["request_id"] == "req-song-1"
    assert captured["audio"] == b"fake-audio"
    assert captured["song_id"] == "12345"
    assert captured["chunk_index"] == 0
    assert captured["key"] == 0
