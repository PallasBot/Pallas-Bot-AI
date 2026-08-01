"""仓根 pretrain → resource/sing/models/pretrain 兼容链接。"""

from __future__ import annotations

from pathlib import Path

from app.media.sing.pretrain_link import ensure_sing_pretrain_cwd_link


def test_ensure_pretrain_link_creates_symlink(tmp_path: Path) -> None:
    target = tmp_path / "resource" / "sing" / "models" / "pretrain" / "nsf_hifigan"
    target.mkdir(parents=True)
    (target / "config.json").write_text("{}", encoding="utf-8")

    assert ensure_sing_pretrain_cwd_link(tmp_path) is True
    link = tmp_path / "pretrain"
    assert link.is_symlink() or link.is_dir()
    assert (link / "nsf_hifigan" / "config.json").is_file()
    # idempotent
    assert ensure_sing_pretrain_cwd_link(tmp_path) is True


def test_ensure_pretrain_link_missing_target(tmp_path: Path) -> None:
    assert ensure_sing_pretrain_cwd_link(tmp_path) is False
