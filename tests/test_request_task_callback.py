from __future__ import annotations

import asyncio

import pytest

from app.tasks.sing import sing_tasks


def test_request_task_callback_includes_song_id(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
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
