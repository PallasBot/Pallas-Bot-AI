from __future__ import annotations

import asyncio
import os
import sys
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


def _install_sing_import_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    asyncer = types.ModuleType("asyncer")
    asyncer.asyncify = lambda fn: fn
    monkeypatch.setitem(sys.modules, "asyncer", asyncer)

    pydub = types.ModuleType("pydub")
    pydub.AudioSegment = type("AudioSegment", (), {})
    monkeypatch.setitem(sys.modules, "pydub", pydub)

    for name in ("pyncm_async", "pyncm_async.apis", "pyncm_async.apis.login", "librosa", "soundfile"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))

    pkg = "app.workers.sing"
    for sub, attrs in {
        "mixer": {"mix": lambda *args, **kwargs: None, "splice": lambda *args, **kwargs: None},
        "ncm_loader": {"download": lambda *args, **kwargs: None},
        "separater": {"separate": lambda *args, **kwargs: None},
        "slicer": {"slice_audio": lambda *args, **kwargs: None},
    }.items():
        module = types.ModuleType(f"{pkg}.{sub}")
        for name, value in attrs.items():
            setattr(module, name, value)
        monkeypatch.setitem(sys.modules, module.__name__, module)

    inference = types.ModuleType("app.media.sing.inference")
    inference.inference = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, inference.__name__, inference)
    monkeypatch.delitem(sys.modules, "app.workers.sing.sing_tasks", raising=False)
    monkeypatch.delitem(sys.modules, "app.workers.sing", raising=False)


def _load_sing_tasks(monkeypatch: pytest.MonkeyPatch):
    _install_sing_import_stubs(monkeypatch)
    from app.workers.sing import sing_tasks  # noqa: PLC0415

    return sing_tasks


def write_cache(path: Path, atime: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"cache")
    os.utime(path, (atime, atime))
    return path


def test_cleanup_reads_policy_dynamically_and_deletes_expired(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.workers.sing import cache_cleanup  # noqa: PLC0415

    now = datetime(2026, 8, 10, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
    old = now.timestamp() - 40 * 86400
    expired = write_cache(tmp_path / "ncm/1.mp3", old)
    policies = iter(({"song_cache_days": 30, "song_cache_size": 0}, {"song_cache_days": 60, "song_cache_size": 0}))
    monkeypatch.setattr(cache_cleanup, "get_sing_defaults", lambda: next(policies))

    first = cache_cleanup.cleanup_cache(root=tmp_path, now=now)
    assert expired in first.removed
    expired = write_cache(tmp_path / "ncm/1.mp3", old)
    second = cache_cleanup.cleanup_cache(root=tmp_path, now=now)
    assert expired.exists()
    assert second.removed == []


def test_cleanup_protects_recent_song_across_stages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.workers.sing import cache_cleanup  # noqa: PLC0415

    now = datetime(2026, 8, 10, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
    old = now.timestamp() - 60 * 86400
    recent = now.timestamp() - 60
    related = [
        write_cache(tmp_path / "ncm/9.mp3", old),
        write_cache(tmp_path / "slices/9_chunk0.mp3", old),
        write_cache(tmp_path / "hdemucs_mmi/9_chunk0/vocals.mp3", old),
        write_cache(tmp_path / "svc/pallas/9_chunk0_0key_pallas.wav", old),
        write_cache(tmp_path / "mix/pallas/9_chunk0_0key_pallas.mp3", old),
        write_cache(tmp_path / "splices/pallas/9_full_0key_pallas.mp3", recent),
    ]
    unrelated = write_cache(tmp_path / "ncm/8.mp3", old)
    monkeypatch.setattr(
        cache_cleanup,
        "get_sing_defaults",
        lambda: {"song_cache_days": 30, "song_cache_size": 1},
    )

    result = cache_cleanup.cleanup_cache(root=tmp_path, now=now)
    assert all(path.exists() for path in related)
    assert unrelated in result.removed
    assert result.protected_song_keys == ("9",)


def test_cleanup_size_zero_and_file_errors_continue(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.workers.sing import cache_cleanup  # noqa: PLC0415

    now = datetime(2026, 8, 10, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
    old = now.timestamp() - 60 * 86400
    failed = write_cache(tmp_path / "splices/pallas/9_full_0key_pallas.mp3", now.timestamp())
    expired = write_cache(tmp_path / "ncm/9.mp3", old)
    skipped = write_cache(tmp_path / "mix/pallas/8_chunk0_0key_pallas.mp3", old)
    monkeypatch.setattr(
        cache_cleanup,
        "get_sing_defaults",
        lambda: {"song_cache_days": 30, "song_cache_size": 0},
    )
    original_stat = Path.stat
    original_unlink = Path.unlink

    def flaky_stat(path: Path, *args, **kwargs):
        if path == skipped:
            raise OSError("stat failed")
        return original_stat(path, *args, **kwargs)

    def flaky_unlink(path: Path, *args, **kwargs):
        if path == expired:
            raise OSError("unlink failed")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)
    monkeypatch.setattr(Path, "unlink", flaky_unlink)
    result = cache_cleanup.cleanup_cache(root=tmp_path, now=now)
    assert failed.exists()
    assert expired in result.failed
    assert skipped in result.failed
    assert result.protected_song_keys == ()


def test_cleanup_scheduler_uses_shanghai_0415() -> None:
    from app.workers.sing.cache_cleanup import cleanup_scheduler  # noqa: PLC0415

    trigger = cleanup_scheduler.get_job("sing-cache-cleanup").trigger
    assert str(trigger.timezone) == "Asia/Shanghai"
    assert str(trigger.fields[5]) == "4"
    assert str(trigger.fields[6]) == "15"


def test_find_stage_cache_prefers_speaker_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sing_tasks = _load_sing_tasks(monkeypatch)

    root = tmp_path / "resource/sing"
    filename = "9_chunk1_0key_amiya.mp3"
    current = root / "mix/amiya" / filename
    legacy = root / "mix" / filename
    current.parent.mkdir(parents=True)
    current.write_bytes(b"current")
    legacy.write_bytes(b"legacy")
    scheduled: list[tuple[str, str, str]] = []

    monkeypatch.setattr(sing_tasks, "SING_ROOT", root)
    monkeypatch.setattr(sing_tasks.archive_legacy_cache_task, "delay", lambda *args: scheduled.append(args))

    assert sing_tasks.find_stage_cache("mix", "amiya", filename) == current
    assert scheduled == []


def test_find_stage_cache_falls_back_and_schedules_archive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sing_tasks = _load_sing_tasks(monkeypatch)

    root = tmp_path / "resource/sing"
    filename = "9_chunk1_0key_amiya.mp3"
    legacy = root / "mix" / filename
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy")
    scheduled: list[tuple[str, str, str]] = []

    monkeypatch.setattr(sing_tasks, "SING_ROOT", root)
    monkeypatch.setattr(sing_tasks.archive_legacy_cache_task, "delay", lambda *args: scheduled.append(args))

    assert sing_tasks.find_stage_cache("mix", "amiya", filename) == legacy
    assert scheduled == [("mix", "amiya", str(legacy))]


def test_sing_task_prefers_speaker_splice_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sing_tasks = _load_sing_tasks(monkeypatch)

    root = tmp_path / "resource/sing"
    filename = "9_full_0key_amiya.mp3"
    current = root / "splices/amiya" / filename
    legacy = root / "splices" / filename
    current.parent.mkdir(parents=True)
    current.write_bytes(b"current")
    legacy.write_bytes(b"legacy")
    callbacks: list[bytes] = []

    async def capture_callback(_request_id: str, audio: bytes, *_args) -> None:
        callbacks.append(audio)

    monkeypatch.setattr(sing_tasks, "SING_ROOT", root)
    monkeypatch.setattr(sing_tasks, "sing_audio_callback", capture_callback)

    assert asyncio.run(sing_tasks._sing_task_async("req", "amiya", 9, 30, 0, 0)) is True
    assert callbacks == [b"current"]


def test_sing_task_archives_legacy_splice_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sing_tasks = _load_sing_tasks(monkeypatch)

    root = tmp_path / "resource/sing"
    legacy = root / "splices/9_full_0key_amiya.mp3"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy")
    callbacks: list[bytes] = []
    scheduled: list[tuple[str, str, str]] = []

    async def capture_callback(_request_id: str, audio: bytes, *_args) -> None:
        callbacks.append(audio)

    monkeypatch.setattr(sing_tasks, "SING_ROOT", root)
    monkeypatch.setattr(sing_tasks, "sing_audio_callback", capture_callback)
    monkeypatch.setattr(sing_tasks.archive_legacy_cache_task, "delay", lambda *args: scheduled.append(args))

    assert asyncio.run(sing_tasks._sing_task_async("req", "amiya", 9, 30, 0, 0)) is True
    assert callbacks == [b"legacy"]
    assert scheduled == [("splices", "amiya", str(legacy))]
