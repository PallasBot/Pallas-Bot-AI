from __future__ import annotations

import app.tasks.media_device as md


def test_cuda_prefix_auto_uses_device(monkeypatch):
    monkeypatch.setattr(md.settings, "media_device", "auto")
    monkeypatch.setattr(md.settings, "sing_cuda_device", 0)
    monkeypatch.setattr(md.platform, "system", lambda: "Linux")
    assert md.media_force_cpu() is False
    # device=0 也应正确绑定（修复旧 `if settings.sing_cuda_device` 在 0 时漏设的 bug）
    assert md.cuda_env_prefix() == "CUDA_VISIBLE_DEVICES=0 "


def test_cuda_prefix_cpu_forces_empty(monkeypatch):
    monkeypatch.setattr(md.settings, "media_device", "cpu")
    monkeypatch.setattr(md.platform, "system", lambda: "Linux")
    assert md.media_force_cpu() is True
    assert md.cuda_env_prefix() == "CUDA_VISIBLE_DEVICES= "


def test_cuda_prefix_windows(monkeypatch):
    monkeypatch.setattr(md.settings, "media_device", "auto")
    monkeypatch.setattr(md.settings, "sing_cuda_device", 1)
    monkeypatch.setattr(md.platform, "system", lambda: "Windows")
    assert md.cuda_env_prefix() == "set CUDA_VISIBLE_DEVICES=1 && "
