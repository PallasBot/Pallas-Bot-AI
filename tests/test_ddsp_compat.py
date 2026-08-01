"""DDSP checkpoint 架构探测与 backend 过滤。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import torch

from app.media.sing import ddsp_compat as dc


def _save_fake_ckpt(path: Path, *, ndim: int) -> None:
    if ndim == 3:
        weight = torch.zeros(1024, 128, 1)
    else:
        weight = torch.zeros(1024, 128)
    torch.save(
        {"model": {dc._PROBE_KEY: weight}},
        path,
    )


def test_probe_distinguishes_conv1d_and_linear(tmp_path: Path) -> None:
    dc.clear_ddsp_arch_cache()
    conv = tmp_path / "conv.pt"
    lin = tmp_path / "lin.pt"
    _save_fake_ckpt(conv, ndim=3)
    _save_fake_ckpt(lin, ndim=2)
    assert dc.probe_ddsp_checkpoint_arch(conv) == dc.ARCH_CONV1D
    assert dc.probe_ddsp_checkpoint_arch(lin) == dc.ARCH_LINEAR


def test_filter_skips_incompatible_preferred_style(tmp_path: Path) -> None:
    dc.clear_ddsp_arch_cache()
    model = tmp_path / "pallas.pt"
    _save_fake_ckpt(model, ndim=3)  # 官方 6.2
    backends = [
        SimpleNamespace(name="ddsp_6.3"),
        SimpleNamespace(name="ddsp_6.2"),
        SimpleNamespace(name="ddsp_6.1"),
        SimpleNamespace(name="sovits_4.1"),
    ]
    kept = dc.filter_backends_by_ddsp_checkpoint(backends, model)
    assert [b.name for b in kept] == ["ddsp_6.2", "ddsp_6.1", "sovits_4.1"]


def test_filter_keeps_linear_for_63(tmp_path: Path) -> None:
    dc.clear_ddsp_arch_cache()
    model = tmp_path / "pallas63.pt"
    _save_fake_ckpt(model, ndim=2)
    backends = [
        SimpleNamespace(name="ddsp_6.3"),
        SimpleNamespace(name="ddsp_6.2"),
    ]
    kept = dc.filter_backends_by_ddsp_checkpoint(backends, model)
    assert [b.name for b in kept] == ["ddsp_6.3"]


def test_backend_matches_unknown_passthrough() -> None:
    assert dc.backend_matches_ddsp_arch("ddsp_6.3", dc.ARCH_UNKNOWN)
    assert dc.backend_matches_ddsp_arch("sovits_4.1", dc.ARCH_CONV1D)
