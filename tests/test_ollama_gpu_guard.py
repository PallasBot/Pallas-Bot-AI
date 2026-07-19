from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.ollama_gpu_guard import (
    GpuCheckResult,
    check_ollama_gpu_sync,
    ensure_ollama_gpu_ready_sync,
    ollama_gpu_guard_enabled,
    probe_inference_gpu_sync,
    reset_ollama_gpu_guard_state_for_tests,
)


@pytest.fixture(autouse=True)
def reset_guard_state() -> None:
    reset_ollama_gpu_guard_state_for_tests()
    yield
    reset_ollama_gpu_guard_state_for_tests()


def test_guard_disabled_for_remote_only() -> None:
    cfg = Settings(llm_chat_enabled=True, llm_provider_mode="remote_only", llm_ollama_gpu_guard=True)
    assert ollama_gpu_guard_enabled(cfg) is False


def test_check_uses_docker_nvml_when_container_gpu_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Settings(
        llm_chat_enabled=True,
        llm_provider_mode="local_only",
        llm_ollama_gpu_guard=True,
        ollama_container="ollama",
    )
    monkeypatch.setattr("app.core.ollama_gpu_guard.ping_local_backend_sync", lambda **_: True)
    monkeypatch.setattr("app.core.ollama_gpu_guard.resolve_ollama_container_name", lambda _: "ollama")
    monkeypatch.setattr("app.core.ollama_gpu_guard.docker_container_has_gpu", lambda _: True)
    monkeypatch.setattr("app.core.ollama_gpu_guard.nvml_ok_in_container", lambda _: True)
    monkeypatch.setattr("app.core.ollama_gpu_guard.ollama_logs_suggest_cpu_fallback", lambda _: False)

    result = check_ollama_gpu_sync(cfg)
    assert result.gpu_ok is True
    assert result.method == "docker_nvml"


def test_check_detects_nvml_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Settings(
        llm_chat_enabled=True,
        llm_provider_mode="local_only",
        llm_ollama_gpu_guard=True,
        ollama_container="ollama",
    )
    monkeypatch.setattr("app.core.ollama_gpu_guard.ping_local_backend_sync", lambda **_: True)
    monkeypatch.setattr("app.core.ollama_gpu_guard.resolve_ollama_container_name", lambda _: "ollama")
    monkeypatch.setattr("app.core.ollama_gpu_guard.docker_container_has_gpu", lambda _: True)
    monkeypatch.setattr("app.core.ollama_gpu_guard.nvml_ok_in_container", lambda _: False)

    result = check_ollama_gpu_sync(cfg)
    assert result.gpu_ok is False
    assert result.detail == "nvml_unavailable"


def test_ensure_auto_recovers_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Settings(
        llm_chat_enabled=True,
        llm_provider_mode="local_only",
        llm_ollama_gpu_guard=True,
        ollama_gpu_auto_recover=True,
        ollama_container="ollama",
    )
    monkeypatch.setattr("app.core.ollama_gpu_guard.recover_cooldown_elapsed", lambda _cfg=None: True)
    calls: list[int] = []

    def fake_check(_cfg=None):
        calls.append(1)
        if len(calls) == 1:
            return GpuCheckResult(
                gpu_ok=False,
                method="docker_nvml",
                detail="nvml_unavailable",
                container="ollama",
            )
        return GpuCheckResult(gpu_ok=True, method="docker_nvml", detail="ok", container="ollama")

    monkeypatch.setattr("app.core.ollama_gpu_guard.check_ollama_gpu_sync", fake_check)
    restarted: list[str] = []
    monkeypatch.setattr(
        "app.core.ollama_gpu_guard.restart_ollama_container_sync",
        lambda name, _cfg=None: restarted.append(name),
    )

    assert ensure_ollama_gpu_ready_sync(cfg=cfg) is True
    assert restarted == ["ollama"]
    assert len(calls) == 2


def test_probe_inference_flags_slow_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Settings(
        llm_chat_enabled=True,
        llm_provider_mode="local_only",
        llm_ollama_gpu_guard=True,
        ollama_gpu_min_tokens_per_sec=20.0,
    )

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, int]:
            return {"eval_count": 4, "eval_duration": 2_000_000_000}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.core.ollama_gpu_guard.httpx.Client", FakeClient)

    result = probe_inference_gpu_sync(cfg)
    assert result.gpu_ok is False
    assert result.method == "inference_probe"
    assert "slow_tps" in result.detail
