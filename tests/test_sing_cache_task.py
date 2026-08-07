from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

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
