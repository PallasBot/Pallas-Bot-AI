from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

GPT_SOVITS_ROOT = Path(__file__).parents[1] / "app/workers/tts/GPT_SoVITS/GPT_SoVITS"


def test_g2pw_uses_cpu_execution_provider() -> None:
    sys.path.insert(0, str(GPT_SOVITS_ROOT))
    try:
        onnx_api = import_module("text.g2pw.onnx_api")
    finally:
        sys.path.remove(str(GPT_SOVITS_ROOT))

    assert onnx_api.G2PW_ONNX_PROVIDERS == ["CPUExecutionProvider"]
