"""SVC registry：解释器与脚本存在性。"""

from __future__ import annotations

import sys
from pathlib import Path

from app.media.sing.registry import (
    ArgStyle,
    ModelBackend,
    SvcRegistry,
    build_command,
    build_env,
    reset_registry_cache,
)


def test_build_env_allows_fairseq_checkpoint_load(monkeypatch) -> None:
    monkeypatch.delenv("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", raising=False)
    env = build_env()
    assert env.get("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD") == "1"


def test_build_command_uses_sys_executable(tmp_path: Path) -> None:
    script = tmp_path / "main_reflow.py"
    script.write_text("# stub\n", encoding="utf-8")
    backend = ModelBackend(
        name="ddsp_6.2",
        script=script,
        arg_style=ArgStyle.DDSP,
        model_glob="*.pt",
    )
    song = tmp_path / "in.wav"
    model = tmp_path / "m.pt"
    out = tmp_path / "out.flac"
    song.write_bytes(b"x")
    model.write_bytes(b"x")
    cmd = build_command(backend, tmp_path, song, out, 0, model)
    assert cmd[0] == sys.executable
    assert cmd[1] == str(script)


def test_compatible_backends_skips_missing_script(tmp_path: Path) -> None:
    reset_registry_cache()
    speaker = tmp_path / "pallas"
    speaker.mkdir()
    (speaker / "pallas.pt").write_bytes(b"x")
    present = tmp_path / "present.py"
    present.write_text("# ok\n", encoding="utf-8")
    missing = tmp_path / "missing.py"
    reg = SvcRegistry(
        backends={
            "gone": ModelBackend(
                name="gone",
                script=missing,
                arg_style=ArgStyle.DDSP,
                model_glob="*.pt",
            ),
            "ok": ModelBackend(
                name="ok",
                script=present,
                arg_style=ArgStyle.DDSP,
                model_glob="*.pt",
            ),
        },
        fallback_order=["gone", "ok"],
    )
    names = [b.name for b in reg.compatible_backends(speaker)]
    assert names == ["ok"]
