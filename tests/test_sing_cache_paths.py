import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _cache_paths(monkeypatch: pytest.MonkeyPatch):
    package = types.ModuleType("app.workers.sing")
    package.__path__ = [str(Path(__file__).parents[1] / "app/workers/sing")]
    monkeypatch.setitem(sys.modules, "app.workers.sing", package)
    spec = importlib.util.find_spec("app.workers.sing.cache_paths")
    assert spec is not None, "speaker cache paths module must exist"
    return importlib.import_module("app.workers.sing.cache_paths")


def test_speaker_stages_nest_outputs_by_speaker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_paths = _cache_paths(monkeypatch)
    root = tmp_path / "resource/sing"

    assert cache_paths.speaker_cache_dir("svc", "amiya", root=root) == root / "svc/amiya"
    assert cache_paths.stage_cache_path("mix", "amiya", "1_chunk0.mp3", root=root) == root / "mix/amiya/1_chunk0.mp3"
    assert cache_paths.speaker_cache_dir("slices", "amiya", root=root) == root / "slices"


def test_legacy_stage_path_stays_flat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_paths = _cache_paths(monkeypatch)
    root = tmp_path / "resource/sing"

    assert cache_paths.legacy_stage_path("splices", "1_full_0key_amiya.mp3", root=root) == (
        root / "splices/1_full_0key_amiya.mp3"
    )


def test_archive_legacy_cache_hardlinks_without_removing_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_paths = _cache_paths(monkeypatch)
    root = tmp_path / "resource/sing"
    legacy = root / "mix/1_chunk0_0key_amiya.mp3"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"audio")

    archived = cache_paths.archive_legacy_cache("mix", "amiya", legacy, root=root)

    assert archived == root / "mix/amiya/1_chunk0_0key_amiya.mp3"
    assert legacy.exists()
    assert archived.read_bytes() == b"audio"
    assert legacy.stat().st_ino == archived.stat().st_ino


def test_archive_legacy_cache_is_idempotent_and_ignores_missing_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_paths = _cache_paths(monkeypatch)
    root = tmp_path / "resource/sing"
    missing = root / "splices/missing.mp3"

    assert cache_paths.archive_legacy_cache("splices", "amiya", missing, root=root) is None
