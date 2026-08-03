"""DDSP 6.3 HuggingFace ContentVec 准备与 config 改写。"""

from __future__ import annotations

from pathlib import Path

from app.media.sing import contentvec_hf as cv


def test_adapt_rewrites_fairseq_encoder_name(tmp_path: Path, monkeypatch) -> None:
    contentvec = tmp_path / "resource/sing/models/pretrain/contentvec"
    contentvec.mkdir(parents=True)
    hf = contentvec / cv.HF_CONTENTVEC_NAME
    hf.write_bytes(b"x" * (cv._MIN_BYTES + 1))

    speaker = tmp_path / "ick"
    speaker.mkdir()
    cfg = speaker / "config.yaml"
    cfg.write_text(
        f"data:\n  encoder_ckpt: pretrain/contentvec/{cv.FAIRSEQ_CONTENTVEC_NAME}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(cv, "ensure_ddsp63_contentvec", lambda root=None: True)
    assert cv.adapt_speaker_config_for_ddsp63(speaker, root=tmp_path) is True
    text = cfg.read_text(encoding="utf-8")
    assert cv.HF_CONTENTVEC_NAME in text
    assert cv.FAIRSEQ_CONTENTVEC_NAME not in text


def test_contentvec_hf_ready(tmp_path: Path) -> None:
    assert cv.contentvec_hf_ready(tmp_path) is False
    dest = cv.contentvec_hf_path(tmp_path)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"x" * (cv._MIN_BYTES + 1))
    assert cv.contentvec_hf_ready(tmp_path) is True
