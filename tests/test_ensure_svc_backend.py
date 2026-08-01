"""DDSP backend 按需拉取。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.media.sing import ensure_backend as eb


def test_describe_present_and_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eb, "repo_root", lambda root=None: tmp_path)
    rel = eb.DDSP_BACKEND_SPECS["ddsp_6.3"]["rel"]
    info = eb.describe_backend_install("ddsp_6.3", root=tmp_path)
    assert info["auto_installable"] is True
    assert info["script_present"] is False

    script = tmp_path / rel / "main_reflow.py"
    script.parent.mkdir(parents=True)
    script.write_text("# stub\n", encoding="utf-8")
    info2 = eb.describe_backend_install("ddsp_6.3", root=tmp_path)
    assert info2["script_present"] is True


def test_ensure_skips_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eb, "repo_root", lambda root=None: tmp_path)
    rel = eb.DDSP_BACKEND_SPECS["ddsp_6.2"]["rel"]
    script = tmp_path / rel / "main_reflow.py"
    script.parent.mkdir(parents=True)
    script.write_text("# stub\n", encoding="utf-8")
    out = eb.ensure_svc_backend("ddsp_6.2", root=tmp_path)
    assert out["ok"] is True
    assert out["status"] == "present"


def test_ensure_clones_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eb, "repo_root", lambda root=None: tmp_path)
    calls: list[list[str]] = []

    def fake_git(args: list[str], *, cwd=None, timeout: float = 600.0):  # noqa: ANN001
        calls.append(list(args))
        if args[:1] == ["clone"]:
            # clone … URL dest
            dest = Path(args[-1])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "main_reflow.py").write_text("# ok\n", encoding="utf-8")
            return 0, "cloned"
        return 1, "no submodule"

    monkeypatch.setattr(eb, "_run_git", fake_git)
    out = eb.ensure_svc_backend("ddsp_6.3", root=tmp_path)
    assert out["ok"] is True
    assert out["status"] == "installed"
    assert any(c[:1] == ["clone"] for c in calls)
    assert (tmp_path / "app/workers/sing/DDSP-SVC-6.3/main_reflow.py").is_file()


def test_ensure_if_needed_noop_for_sovits() -> None:
    assert eb.ensure_svc_backend_if_needed("sovits_4.1") is None


def test_ensure_unsupported() -> None:
    out = eb.ensure_svc_backend("sovits_4.1")
    assert out["ok"] is False
    assert out["status"] == "unsupported"
