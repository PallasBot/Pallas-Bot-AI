"""按音色绑定 SVC backend。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.media import models as mm


def test_resolve_preferred_backend_speaker_overrides_global(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(mm, "repo_root", lambda root=None: tmp_path)
    path = tmp_path / "data" / "media_models.json"
    path.write_text(
        '{"sing":{"default_speaker":"pallas","preferred_backend":"ddsp_6.3",'
        '"speaker_backends":{"pallas":"ddsp_6.2","other":"ddsp_6.1"}}}\n',
        encoding="utf-8",
    )
    assert mm.resolve_preferred_backend("pallas", root=tmp_path) == "ddsp_6.2"
    assert mm.resolve_preferred_backend("other", root=tmp_path) == "ddsp_6.1"
    assert mm.resolve_preferred_backend("missing", root=tmp_path) == "ddsp_6.3"
    assert mm.resolve_preferred_backend(root=tmp_path) == "ddsp_6.3"


def test_set_speaker_backends_replace_and_clear(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_DEPLOY_MODE", "source")
    (tmp_path / "data").mkdir()
    for name in ("pallas", "other"):
        speaker = tmp_path / "resource/sing/models" / name
        speaker.mkdir(parents=True)
        (speaker / f"{name}.pt").write_bytes(b"x")
    monkeypatch.setattr(mm, "repo_root", lambda root=None: tmp_path)
    monkeypatch.setattr(mm.settings, "svc_models_root", "resource/sing/models")
    monkeypatch.setattr(
        mm,
        "list_svc_backends",
        lambda root=None: {
            "backends": [
                {"id": "ddsp_6.1", "enabled": True},
                {"id": "ddsp_6.2", "enabled": True},
                {"id": "ddsp_6.3", "enabled": True},
            ],
        },
    )
    monkeypatch.setattr(
        "app.media.sing.ensure_backend.schedule_ensure_svc_backend",
        lambda *a, **k: {"ok": True, "status": "present"},
    )

    out = mm.set_sing_defaults(
        speaker_backends={"pallas": "ddsp_6.2", "other": "ddsp_6.1"},
        root=tmp_path,
    )
    assert out["speaker_backends"]["pallas"] == "ddsp_6.2"
    assert out["speaker_backends"]["other"] == "ddsp_6.1"

    # 整表替换：未再提交的键清掉；空串表示该音色改回全局
    out2 = mm.set_sing_defaults(
        speaker_backends={"pallas": "", "other": "ddsp_6.2"},
        root=tmp_path,
    )
    assert "pallas" not in out2["speaker_backends"]
    assert out2["speaker_backends"]["other"] == "ddsp_6.2"

    out3 = mm.set_sing_defaults(speaker_backends={}, root=tmp_path)
    assert out3["speaker_backends"] == {}
