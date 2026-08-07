import os
from pathlib import Path

SING_ROOT = Path("resource/sing")
SPEAKER_STAGES = frozenset({"svc", "mix", "splices"})


def speaker_cache_dir(stage: str, speaker: str, *, root: Path = SING_ROOT) -> Path:
    base = root / stage
    return base / speaker if stage in SPEAKER_STAGES else base


def stage_cache_path(stage: str, speaker: str, filename: str, *, root: Path = SING_ROOT) -> Path:
    return speaker_cache_dir(stage, speaker, root=root) / filename


def legacy_stage_path(stage: str, filename: str, *, root: Path = SING_ROOT) -> Path:
    return root / stage / filename


def archive_legacy_cache(stage: str, speaker: str, legacy: Path, *, root: Path = SING_ROOT) -> Path | None:
    if stage not in SPEAKER_STAGES or not legacy.is_file():
        return None

    target = stage_cache_path(stage, speaker, legacy.name, root=root)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(legacy, target)
    except FileExistsError:
        pass
    except OSError:
        return None

    return target if target.is_file() else None
