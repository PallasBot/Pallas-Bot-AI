from __future__ import annotations

import os
from pathlib import Path

import pytest

import app.workers.media_device as md
from app.workers.sing import separater


class _FakeGPUHandle:
    def __init__(self, captured: list[str]) -> None:
        self._captured = captured

    def run_subprocess(self, cmd: str) -> int:
        self._captured.append(cmd)
        return 0


class _FakeLocker:
    def __init__(self, captured: list[str]) -> None:
        self._captured = captured

    def acquire(self, **_kwargs):
        captured = self._captured

        class _Ctx:
            def __enter__(self):
                return _FakeGPUHandle(captured)

            def __exit__(self, *exc):
                return False

        return _Ctx()


def _run_separate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, system: str, *, media_device: str, device: int
) -> str:
    monkeypatch.setattr(separater.platform, "system", lambda: system)
    monkeypatch.setattr(md.settings, "media_device", media_device)
    monkeypatch.setattr(md.settings, "sing_cuda_device", device)
    captured: list[str] = []
    song = tmp_path / "9.mp3"
    song.write_bytes(b"x")
    separater.separate(song, tmp_path / "out", key=0, locker=_FakeLocker(captured))
    assert len(captured) == 1
    return captured[0]


def test_separate_unix_prefix_sets_offline_and_keeps_cuda(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cmd = _run_separate(monkeypatch, tmp_path, "Linux", media_device="auto", device=0)
    assert cmd.startswith("CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 ")
    assert "-m demucs" in cmd


def test_separate_windows_prefix_quotes_offline_and_keeps_cuda(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cmd = _run_separate(monkeypatch, tmp_path, "Windows", media_device="auto", device=1)
    assert cmd.startswith('set CUDA_VISIBLE_DEVICES=1 && set "HF_HUB_OFFLINE=1" && ')
    assert "-m demucs" in cmd


def test_separate_cpu_hides_gpu_and_still_sets_offline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    unix = _run_separate(monkeypatch, tmp_path, "Linux", media_device="cpu", device=0)
    assert unix.startswith("CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 ")

    windows = _run_separate(monkeypatch, tmp_path, "Windows", media_device="cpu", device=0)
    assert windows.startswith('set CUDA_VISIBLE_DEVICES= && set "HF_HUB_OFFLINE=1" && ')


def test_separate_leaves_parent_hf_hub_offline_untouched(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    _run_separate(monkeypatch, tmp_path, "Linux", media_device="auto", device=0)
    assert "HF_HUB_OFFLINE" not in os.environ
