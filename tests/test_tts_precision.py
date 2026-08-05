from __future__ import annotations

import importlib.util
from pathlib import Path

import torch

GPT_SOVITS_ROOT = Path(__file__).parents[1] / "app/workers/tts/GPT_SoVITS/GPT_SoVITS"


def test_coerce_input_to_model_dtype_uses_model_parameter_dtype() -> None:
    module_path = GPT_SOVITS_ROOT / "TTS_infer_pack/precision.py"
    spec = importlib.util.spec_from_file_location("tts_precision", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    model = torch.nn.Conv1d(1, 1, 1).half()
    input_values = torch.zeros(1, 16000, dtype=torch.float32)

    result = module.coerce_input_to_model_dtype(input_values, model)

    assert result.dtype is torch.float16
    assert result.device == input_values.device
