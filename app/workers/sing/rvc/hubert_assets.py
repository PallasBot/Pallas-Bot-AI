"""RVC HuBERT：Transformers 目录校验，以及 fairseq .pt → Transformers 转换。"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import torch
from torch import nn
from transformers import HubertConfig, HubertModel

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)
logging.getLogger("fairseq").setLevel(logging.WARNING)


class HubertModelWithFinalProj(HubertModel):
    def __init__(self, config):
        super().__init__(config)
        self.final_proj = nn.Linear(config.hidden_size, config.classifier_proj_size)


DEFAULT_PREPROCESSOR = {
    "do_normalize": False,
    "feature_extractor_type": "Wav2Vec2FeatureExtractor",
    "feature_size": 1,
    "padding_side": "right",
    "padding_value": 0.0,
    "return_attention_mask": False,
    "sampling_rate": 16000,
}


def build_mapping() -> dict[str, str]:
    mapping = {
        "masked_spec_embed": "mask_emb",
        "encoder.layer_norm.bias": "encoder.layer_norm.bias",
        "encoder.layer_norm.weight": "encoder.layer_norm.weight",
        "encoder.pos_conv_embed.conv.bias": "encoder.pos_conv.0.bias",
        "encoder.pos_conv_embed.conv.weight_g": "encoder.pos_conv.0.weight_g",
        "encoder.pos_conv_embed.conv.weight_v": "encoder.pos_conv.0.weight_v",
        "feature_projection.layer_norm.bias": "layer_norm.bias",
        "feature_projection.layer_norm.weight": "layer_norm.weight",
        "feature_projection.projection.bias": "post_extract_proj.bias",
        "feature_projection.projection.weight": "post_extract_proj.weight",
        "final_proj.bias": "final_proj.bias",
        "final_proj.weight": "final_proj.weight",
    }
    for layer in range(12):
        for j in ("q", "k", "v"):
            mapping[f"encoder.layers.{layer}.attention.{j}_proj.weight"] = (
                f"encoder.layers.{layer}.self_attn.{j}_proj.weight"
            )
            mapping[f"encoder.layers.{layer}.attention.{j}_proj.bias"] = (
                f"encoder.layers.{layer}.self_attn.{j}_proj.bias"
            )
        mapping[f"encoder.layers.{layer}.final_layer_norm.bias"] = (
            f"encoder.layers.{layer}.final_layer_norm.bias"
        )
        mapping[f"encoder.layers.{layer}.final_layer_norm.weight"] = (
            f"encoder.layers.{layer}.final_layer_norm.weight"
        )
        mapping[f"encoder.layers.{layer}.layer_norm.bias"] = (
            f"encoder.layers.{layer}.self_attn_layer_norm.bias"
        )
        mapping[f"encoder.layers.{layer}.layer_norm.weight"] = (
            f"encoder.layers.{layer}.self_attn_layer_norm.weight"
        )
        mapping[f"encoder.layers.{layer}.attention.out_proj.bias"] = (
            f"encoder.layers.{layer}.self_attn.out_proj.bias"
        )
        mapping[f"encoder.layers.{layer}.attention.out_proj.weight"] = (
            f"encoder.layers.{layer}.self_attn.out_proj.weight"
        )
        mapping[f"encoder.layers.{layer}.feed_forward.intermediate_dense.bias"] = (
            f"encoder.layers.{layer}.fc1.bias"
        )
        mapping[f"encoder.layers.{layer}.feed_forward.intermediate_dense.weight"] = (
            f"encoder.layers.{layer}.fc1.weight"
        )
        mapping[f"encoder.layers.{layer}.feed_forward.output_dense.bias"] = (
            f"encoder.layers.{layer}.fc2.bias"
        )
        mapping[f"encoder.layers.{layer}.feed_forward.output_dense.weight"] = (
            f"encoder.layers.{layer}.fc2.weight"
        )
    for layer in range(7):
        mapping[f"feature_extractor.conv_layers.{layer}.conv.weight"] = (
            f"feature_extractor.conv_layers.{layer}.0.weight"
        )
        if layer == 0:
            mapping[f"feature_extractor.conv_layers.{layer}.layer_norm.weight"] = (
                f"feature_extractor.conv_layers.{layer}.2.weight"
            )
            mapping[f"feature_extractor.conv_layers.{layer}.layer_norm.bias"] = (
                f"feature_extractor.conv_layers.{layer}.2.bias"
            )
    return mapping


def hubert_transformers_ready(directory: Path) -> bool:
    return (directory / "config.json").is_file() and (
        (directory / "pytorch_model.bin").is_file() or (directory / "model.safetensors").is_file()
    )


def resolve_fairseq_hubert(pretrain_rvc: Path) -> Path | None:
    for path in (
        pretrain_rvc / "hubert_base" / "hubert_base.pt",
        pretrain_rvc / "hubert_base.pt",
    ):
        if path.is_file():
            return path
    return None


def convert_hubert(src: Path, out: Path, *, skip_sanity: bool = False) -> Path:
    from fairseq import checkpoint_utils  # noqa: PLC0415

    if not src.is_file():
        raise FileNotFoundError(f"fairseq HuBERT 不存在: {src}")
    out.mkdir(parents=True, exist_ok=True)

    models, _, _ = checkpoint_utils.load_model_ensemble_and_task([str(src)], suffix="")
    fs_model = models[0].eval()

    if (out / "config.json").is_file():
        config = HubertConfig.from_pretrained(str(out))
    else:
        config = HubertConfig()
    config.torch_dtype = "float32"
    config.architectures = ["HubertModelWithFinalProj"]

    hubert = HubertModelWithFinalProj(config)
    mapping = build_mapping()
    fs_sd = fs_model.state_dict()
    new_sd = {hf: fs_sd[fs] for hf, fs in mapping.items()}
    missing = hubert.load_state_dict(new_sd, strict=False)
    if missing.missing_keys:
        raise RuntimeError(f"转换缺键: {missing.missing_keys}")

    hubert.eval()
    if not skip_sanity:
        with torch.no_grad():
            x = torch.randn(1, 16384)
            r1 = hubert(x, output_hidden_states=True)["hidden_states"][9]
            r1 = hubert.final_proj(r1)
            r2 = fs_model.extract_features(
                source=x,
                padding_mask=torch.zeros(1, 16384, dtype=torch.bool),
                output_layer=9,
            )[0]
            r2 = fs_model.final_proj(r2)
            if not torch.allclose(r1, r2, atol=1e-3):
                raise RuntimeError(f"转换校验失败 max_diff={(r1 - r2).abs().max().item()}")

    hubert.save_pretrained(str(out), safe_serialization=False)
    if not (out / "preprocessor_config.json").is_file():
        (out / "preprocessor_config.json").write_text(
            json.dumps(DEFAULT_PREPROCESSOR, indent=2) + "\n",
            encoding="utf-8",
        )
    bin_path = out / "pytorch_model.bin"
    if not bin_path.is_file():
        raise RuntimeError(f"未写出 {bin_path}")
    logger.info("RVC HuBERT 已从 fairseq 转换: %s -> %s", src, bin_path)
    return bin_path


def ensure_hubert_transformers(pretrain_rvc: Path) -> Path:
    """保证 ``pretrain_rvc/hubert_base/`` 为 Transformers 布局；必要时从 .pt 转换。"""
    out = pretrain_rvc / "hubert_base"
    if hubert_transformers_ready(out):
        return out
    src = resolve_fairseq_hubert(pretrain_rvc)
    if src is None:
        raise FileNotFoundError(
            "缺少 RVC HuBERT：请下载 Transformers 目录 "
            f"{out}/（含 config.json + pytorch_model.bin），"
            "或放置 fairseq hubert_base.pt 后执行 "
            "`uv run python tools/convert_rvc_hubert.py`。"
            "来源：https://huggingface.co/lj1995/VoiceConversionWebUI"
        )
    logger.warning("RVC HuBERT 仅为 fairseq .pt，正在转换为 Transformers 目录: %s", src)
    convert_hubert(src, out)
    return out
