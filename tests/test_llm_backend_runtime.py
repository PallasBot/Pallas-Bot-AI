from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.core.llm_backend_runtime import (
    get_llm_model,
    get_llm_num_gpu,
    is_llm_gpu_config_dirty,
    reload_llm_runtime_from_env,
    set_llm_num_gpu,
    switch_llm_model,
    switch_llm_num_gpu,
)


def test_get_llm_num_gpu_from_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runtime_file = tmp_path / "llm_runtime.json"
    runtime_file.write_text('{"model": "qwen3.5:9b", "num_gpu": 70}', encoding="utf-8")
    monkeypatch.setattr("app.core.llm_backend_runtime._RUNTIME_FILE", runtime_file)
    monkeypatch.setattr("app.core.llm_backend_runtime.settings.llm_num_gpu", 12)

    assert get_llm_num_gpu() == 70


def test_reload_llm_runtime_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runtime_file = tmp_path / "llm_runtime.json"
    monkeypatch.setattr("app.core.llm_backend_runtime._RUNTIME_FILE", runtime_file)
    monkeypatch.setattr("app.core.llm_backend_runtime.settings.log_path", str(tmp_path))

    fresh = type("FreshSettings", (), {"llm_model": "qwen2.5:7b", "llm_num_gpu": 99})()
    monkeypatch.setattr("app.core.llm_backend_runtime.Settings", lambda: fresh)

    model, num_gpu = reload_llm_runtime_from_env()
    assert model == "qwen2.5:7b"
    assert num_gpu == 99
    assert get_llm_model() == "qwen2.5:7b"
    assert get_llm_num_gpu() == 99


def test_set_llm_num_gpu_marks_dirty(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runtime_file = tmp_path / "llm_runtime.json"
    runtime_file.write_text('{"model": "qwen3.5:9b", "num_gpu": 12}', encoding="utf-8")
    monkeypatch.setattr("app.core.llm_backend_runtime._RUNTIME_FILE", runtime_file)

    assert is_llm_gpu_config_dirty() is False
    set_llm_num_gpu(70)
    assert is_llm_gpu_config_dirty() is True


def test_switch_llm_model_unloads_before_set(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runtime_file = tmp_path / "llm_runtime.json"
    monkeypatch.setattr("app.core.llm_backend_runtime._RUNTIME_FILE", runtime_file)
    monkeypatch.setattr("app.core.llm_backend_runtime.settings.log_path", str(tmp_path))

    unload = AsyncMock(return_value=(200, ""))
    pull = AsyncMock()

    async def run() -> str:
        with (
            patch("app.core.llm_backend_runtime.unload_resident_backend_model", unload),
            patch("app.core.llm_backend_runtime.pull_local_backend_model", pull),
        ):
            return await switch_llm_model("qwen3.5:9b", pull=False)

    result = asyncio.run(run())

    assert result == "qwen3.5:9b"
    unload.assert_awaited_once_with()
    pull.assert_not_awaited()
    data = json.loads(runtime_file.read_text(encoding="utf-8"))
    assert data["model"] == "qwen3.5:9b"
    assert data.get("gpu_config_dirty") is True


def test_switch_llm_num_gpu_unloads_and_marks_dirty(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    runtime_file = tmp_path / "llm_runtime.json"
    runtime_file.write_text('{"model": "qwen3.5:9b", "num_gpu": 12}', encoding="utf-8")
    monkeypatch.setattr("app.core.llm_backend_runtime._RUNTIME_FILE", runtime_file)

    unload = AsyncMock(return_value=(200, ""))

    async def run() -> int:
        with patch("app.core.llm_backend_runtime.unload_resident_backend_model", unload):
            return await switch_llm_num_gpu(24)

    result = asyncio.run(run())

    assert result == 24
    unload.assert_awaited_once_with()
    data = json.loads(runtime_file.read_text(encoding="utf-8"))
    assert data["num_gpu"] == 24
    assert data.get("gpu_config_dirty") is True
