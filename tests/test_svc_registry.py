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
    resolve_rvc_index,
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


def test_resolve_rvc_index_prefers_same_stem(tmp_path: Path) -> None:
    speaker = tmp_path / "amiya"
    speaker.mkdir()
    model = speaker / "amiya_v2.pth"
    model.write_bytes(b"x")
    (speaker / "other.index").write_bytes(b"i")
    same = speaker / "amiya_v2.index"
    same.write_bytes(b"i")
    assert resolve_rvc_index(model, speaker) == same


def test_resolve_rvc_index_single_index_fallback(tmp_path: Path) -> None:
    speaker = tmp_path / "lappland"
    speaker.mkdir()
    model = speaker / "model.pth"
    model.write_bytes(b"x")
    only = speaker / "added_IVF.index"
    only.write_bytes(b"i")
    assert resolve_rvc_index(model, speaker) == only


def test_build_command_rvc_includes_index(tmp_path: Path) -> None:
    script = tmp_path / "infer_rvc.py"
    script.write_text("# stub\n", encoding="utf-8")
    speaker = tmp_path / "spk"
    speaker.mkdir()
    model = speaker / "voice.pth"
    index = speaker / "voice.index"
    song = tmp_path / "in.wav"
    out = tmp_path / "out.flac"
    model.write_bytes(b"x")
    index.write_bytes(b"i")
    song.write_bytes(b"x")
    backend = ModelBackend(
        name="rvc",
        script=script,
        arg_style=ArgStyle.RVC,
        model_glob="*.pth",
    )
    cmd = build_command(backend, speaker, song, out, 3, model)
    assert cmd[0] == sys.executable
    assert "-k" in cmd
    assert cmd[cmd.index("-k") + 1] == "3"
    assert "--index" in cmd
    assert cmd[cmd.index("--index") + 1] == str(index.resolve())


def test_compatible_backends_rvc_pth_not_ddsp_pt(tmp_path: Path) -> None:
    reset_registry_cache()
    speaker = tmp_path / "rvc_spk"
    speaker.mkdir()
    (speaker / "char.pth").write_bytes(b"x")
    ddsp_script = tmp_path / "ddsp.py"
    rvc_script = tmp_path / "rvc.py"
    ddsp_script.write_text("#\n", encoding="utf-8")
    rvc_script.write_text("#\n", encoding="utf-8")
    reg = SvcRegistry(
        backends={
            "ddsp_6.2": ModelBackend(
                name="ddsp_6.2",
                script=ddsp_script,
                arg_style=ArgStyle.DDSP,
                model_glob="*.pt",
            ),
            "rvc": ModelBackend(
                name="rvc",
                script=rvc_script,
                arg_style=ArgStyle.RVC,
                model_glob="*.pth",
            ),
        },
        fallback_order=["ddsp_6.2", "rvc"],
    )
    names = [b.name for b in reg.compatible_backends(speaker)]
    assert names == ["rvc"]
