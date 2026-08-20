"""DDSP-SVC 6.3 所需的 HuggingFace ContentVec。

6.1/6.2 用 fairseq ``checkpoint_best_legacy_500.pt``；
6.3 改为 ``HubertModel.load_state_dict``，官方默认
``pretrain/contentvec/pytorch_model.bin``
（https://huggingface.co/lengyue233/content-vec-best）。
社区权重的 config 常仍写 legacy 文件名，需在推理前改写并补齐权重。
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING
from urllib.request import urlretrieve

from app.core.logger import logger
from app.media.assets import repo_root

if TYPE_CHECKING:
    from pathlib import Path

FAIRSEQ_CONTENTVEC_NAME = "checkpoint_best_legacy_500.pt"
HF_CONTENTVEC_NAME = "pytorch_model.bin"

_REL_HF = f"resource/sing/models/pretrain/contentvec/{HF_CONTENTVEC_NAME}"
_MIN_BYTES = 50 * 1024 * 1024

_CONTENTVEC_URLS: tuple[str, ...] = (
    "https://hf-mirror.com/lengyue233/content-vec-best/resolve/main/pytorch_model.bin",
    "https://huggingface.co/lengyue233/content-vec-best/resolve/main/pytorch_model.bin",
)

_lock = threading.Lock()


def contentvec_hf_path(root: Path | None = None) -> Path:
    return repo_root(root) / _REL_HF


def contentvec_hf_ready(root: Path | None = None) -> bool:
    path = contentvec_hf_path(root)
    try:
        return path.is_file() and path.stat().st_size >= _MIN_BYTES
    except OSError:
        return False


def ensure_ddsp63_contentvec(root: Path | None = None) -> bool:
    """确保 HF ContentVec 落盘；已存在则直接 True。"""
    if contentvec_hf_ready(root):
        return True
    with _lock:
        if contentvec_hf_ready(root):
            return True
        dest = contentvec_hf_path(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".download")
        last_err = ""
        for url in _CONTENTVEC_URLS:
            try:
                if tmp.exists():
                    tmp.unlink()
                logger.info("downloading DDSP 6.3 ContentVec: {} -> {}", url, dest)
                urlretrieve(url, tmp)  # noqa: S310 — 固定镜像列表
                if tmp.stat().st_size < _MIN_BYTES:
                    last_err = f"文件过小 ({tmp.stat().st_size} bytes): {url}"
                    tmp.unlink(missing_ok=True)
                    continue
                tmp.replace(dest)
                logger.info("DDSP 6.3 ContentVec ready: {}", dest)
                return True
            except Exception as exc:
                last_err = str(exc)
                logger.warning("ContentVec download failed url={} err={}", url, exc)
                tmp.unlink(missing_ok=True)
        logger.error("DDSP 6.3 ContentVec download failed: {}", last_err)
        return False


def adapt_speaker_config_for_ddsp63(speaker_dir: Path, *, root: Path | None = None) -> bool:
    """补齐 HF 权重，并把 speaker config 里的 fairseq 文件名改成 pytorch_model.bin。"""
    if not ensure_ddsp63_contentvec(root):
        return False

    cfg_path = speaker_dir / "config.yaml"
    if not cfg_path.is_file():
        logger.warning("speaker={} lacks config.yaml, DDSP 6.3 cannot load", speaker_dir.name)
        return False

    try:
        text = cfg_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("failed to read {}: {}", cfg_path, exc)
        return False

    if HF_CONTENTVEC_NAME in text and FAIRSEQ_CONTENTVEC_NAME not in text:
        return True
    if FAIRSEQ_CONTENTVEC_NAME not in text:
        # 已是其他路径；只要 HF 文件在 pretrain 链接下通常仍可被相对路径找到
        return True

    new_text = text.replace(FAIRSEQ_CONTENTVEC_NAME, HF_CONTENTVEC_NAME)
    try:
        cfg_path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        logger.warning("failed to write {}: {}", cfg_path, exc)
        return False
    logger.info(
        "speaker={} encoder_ckpt switched from {} to {} (DDSP 6.3)",
        speaker_dir.name,
        FAIRSEQ_CONTENTVEC_NAME,
        HF_CONTENTVEC_NAME,
    )
    return True
