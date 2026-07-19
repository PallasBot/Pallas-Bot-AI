"""Ollama GPU 探活与自动恢复（容器 NVML 断联 → 推理回退 CPU）。"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings, settings
from app.core.llm_backend_runtime import (
    local_backend_generate_url,
    ping_local_backend_sync,
    wait_local_backend_ready_sync,
)
from app.core.logger import logger

_KNOWN_CONTAINERS = ("pallas-ai-ollama", "pallas-full-ollama", "ollama", "pallas-ollama")
_state_lock = threading.Lock()
_last_check_monotonic = 0.0
_last_recover_monotonic = 0.0
_recover_count = 0
_last_snapshot: dict[str, Any] = {
    "enabled": False,
    "gpu_ok": None,
    "method": "skipped",
    "detail": "not_checked",
    "container": None,
    "auto_recover": False,
    "recover_count": 0,
    "last_check_at": None,
    "last_recover_at": None,
}
_bg_thread: threading.Thread | None = None
_bg_stop = threading.Event()


@dataclass
class GpuCheckResult:
    gpu_ok: bool
    method: str
    detail: str
    container: str | None = None


def ollama_gpu_guard_enabled(cfg: Settings | None = None) -> bool:
    c = cfg or settings
    if not (c.llm_ollama_gpu_guard and c.llm_chat_enabled):
        return False
    mode = str(c.llm_provider_mode or "local_only").strip().lower()
    return mode in ("local_only", "chain")


def ollama_gpu_snapshot() -> dict[str, Any]:
    with _state_lock:
        return dict(_last_snapshot)


def resolve_ollama_container_name(cfg: Settings | None = None) -> str | None:
    c = cfg or settings
    explicit = (c.ollama_container or "").strip()
    if explicit:
        return explicit
    if not shutil.which("docker"):
        return None
    for name in _KNOWN_CONTAINERS:
        if docker_container_running(name):
            return name
    try:
        proc = subprocess.run(
            ["docker", "ps", "--filter", "ancestor=ollama/ollama", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in proc.stdout.splitlines():
        name = line.strip()
        if name:
            return name
    return None


def docker_container_running(name: str) -> bool:
    if not name or not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def docker_container_has_gpu(name: str) -> bool:
    if not name or not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "inspect", "-f", "{{json .HostConfig.DeviceRequests}}", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    body = proc.stdout.strip()
    return body not in ("", "null", "[]") and "gpu" in body


def nvml_ok_in_container(name: str) -> bool:
    if not name or not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "exec", name, "nvidia-smi"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def ollama_logs_suggest_cpu_fallback(name: str) -> bool:
    if not name or not shutil.which("docker"):
        return False
    try:
        proc = subprocess.run(
            ["docker", "logs", name, "--tail", "200"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    text = proc.stdout + proc.stderr
    markers = (
        "no CUDA-capable device is detected",
        "Failed to initialize NVML",
        "failure during GPU discovery",
    )
    return any(marker in text for marker in markers)


def probe_model_name(cfg: Settings | None = None) -> str:
    c = cfg or settings
    probe = (c.ollama_gpu_probe_model or "").strip()
    if probe:
        return probe
    categorizer = (c.llm_categorizer_model or "").strip()
    if categorizer:
        return categorizer
    return (c.llm_model or "qwen2.5:0.5b").strip() or "qwen2.5:0.5b"


def probe_inference_gpu_sync(cfg: Settings | None = None) -> GpuCheckResult:
    c = cfg or settings
    model = probe_model_name(c)
    payload = {
        "model": model,
        "prompt": "1",
        "stream": False,
        "options": {"num_predict": max(4, int(c.ollama_gpu_probe_tokens))},
    }
    wall_start = time.monotonic()
    try:
        with httpx.Client(timeout=httpx.Timeout(c.ollama_gpu_probe_timeout)) as client:
            response = client.post(local_backend_generate_url(), json=payload)
    except httpx.HTTPError as exc:
        return GpuCheckResult(gpu_ok=True, method="inference_probe", detail=f"probe_http_error={exc}")
    if response.status_code != 200:
        return GpuCheckResult(
            gpu_ok=True,
            method="inference_probe",
            detail=f"probe_status={response.status_code}",
        )
    try:
        data = response.json()
    except ValueError:
        return GpuCheckResult(gpu_ok=True, method="inference_probe", detail="probe_invalid_json")
    eval_count = int(data.get("eval_count") or 0)
    eval_duration_ns = int(data.get("eval_duration") or 0)
    wall = time.monotonic() - wall_start
    if eval_count > 0 and eval_duration_ns > 0:
        tps = eval_count / (eval_duration_ns / 1e9)
        if tps < float(c.ollama_gpu_min_tokens_per_sec):
            return GpuCheckResult(
                gpu_ok=False,
                method="inference_probe",
                detail=f"slow_tps={tps:.2f} model={model}",
            )
        return GpuCheckResult(
            gpu_ok=True,
            method="inference_probe",
            detail=f"tps={tps:.1f} model={model}",
        )
    if wall >= float(c.ollama_gpu_probe_slow_wall_sec):
        return GpuCheckResult(
            gpu_ok=False,
            method="inference_probe",
            detail=f"slow_wall={wall:.1f}s model={model}",
        )
    return GpuCheckResult(gpu_ok=True, method="inference_probe", detail=f"wall={wall:.1f}s inconclusive")


def check_ollama_gpu_sync(cfg: Settings | None = None) -> GpuCheckResult:
    c = cfg or settings
    if not ollama_gpu_guard_enabled(c):
        return GpuCheckResult(gpu_ok=True, method="skipped", detail="guard_disabled")

    if not ping_local_backend_sync(timeout_sec=2.0):
        return GpuCheckResult(gpu_ok=True, method="skipped", detail="backend_unreachable")

    container = resolve_ollama_container_name(c)
    if container and docker_container_has_gpu(container):
        if not nvml_ok_in_container(container):
            return GpuCheckResult(
                gpu_ok=False,
                method="docker_nvml",
                detail="nvml_unavailable",
                container=container,
            )
        if ollama_logs_suggest_cpu_fallback(container):
            return GpuCheckResult(
                gpu_ok=False,
                method="docker_nvml",
                detail="cuda_cpu_fallback_logs",
                container=container,
            )
        return GpuCheckResult(gpu_ok=True, method="docker_nvml", detail="ok", container=container)

    backend_host = urlparse(c.llm_backend_url).hostname or ""
    if backend_host not in ("127.0.0.1", "localhost", "ollama") and not container:
        return GpuCheckResult(gpu_ok=True, method="skipped", detail="remote_backend_host")

    return probe_inference_gpu_sync(c)


def restart_ollama_container_sync(name: str, cfg: Settings | None = None) -> None:
    c = cfg or settings
    if not name or not shutil.which("docker"):
        msg = "docker unavailable for ollama gpu recover"
        raise RuntimeError(msg)
    logger.warning("ollama gpu recover: restarting container {}", name)
    try:
        proc = subprocess.run(
            ["docker", "restart", name],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        msg = f"docker restart failed: {exc}"
        raise RuntimeError(msg) from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        msg = f"docker restart {name} exit {proc.returncode}: {detail}"
        raise RuntimeError(msg)
    wait_local_backend_ready_sync(float(c.ollama_gpu_recover_wait_sec))
    if docker_container_has_gpu(name) and not nvml_ok_in_container(name):
        msg = f"ollama container {name} still has NVML failure after restart"
        raise RuntimeError(msg)


def recover_cooldown_elapsed(cfg: Settings | None = None) -> bool:
    c = cfg or settings
    with _state_lock:
        if _last_recover_monotonic <= 0:
            return True
        return (time.monotonic() - _last_recover_monotonic) >= float(c.ollama_gpu_recover_cooldown_sec)


def record_snapshot(result: GpuCheckResult, *, recovered: bool = False) -> None:
    global _last_check_monotonic, _last_recover_monotonic, _recover_count, _last_snapshot  # noqa: PLW0603
    now = time.time()
    with _state_lock:
        previous_recover_at = _last_snapshot.get("last_recover_at")
        _last_check_monotonic = time.monotonic()
        if recovered:
            _last_recover_monotonic = time.monotonic()
            _recover_count += 1
        _last_snapshot = {
            "enabled": ollama_gpu_guard_enabled(),
            "gpu_ok": result.gpu_ok,
            "method": result.method,
            "detail": result.detail,
            "container": result.container,
            "auto_recover": bool(settings.ollama_gpu_auto_recover),
            "recover_count": _recover_count,
            "last_check_at": now,
            "last_recover_at": now if recovered else previous_recover_at,
        }


def ensure_ollama_gpu_ready_sync(*, fix: bool | None = None, cfg: Settings | None = None) -> bool:
    c = cfg or settings
    if not ollama_gpu_guard_enabled(c):
        result = GpuCheckResult(gpu_ok=True, method="skipped", detail="guard_disabled")
        record_snapshot(result)
        return True

    result = check_ollama_gpu_sync(c)
    if result.gpu_ok:
        record_snapshot(result)
        return True

    should_fix = bool(c.ollama_gpu_auto_recover if fix is None else fix)
    record_snapshot(result)
    if not should_fix:
        logger.warning(
            "ollama gpu check failed ({}/{}); auto recover disabled",
            result.method,
            result.detail,
        )
        return False

    if not recover_cooldown_elapsed(c):
        logger.warning(
            "ollama gpu check failed ({}/{}); recover skipped (cooldown)",
            result.method,
            result.detail,
        )
        return False

    container = result.container or resolve_ollama_container_name(c)
    if not container:
        logger.error(
            "ollama gpu check failed ({}/{}); no container to restart (set OLLAMA_CONTAINER)",
            result.method,
            result.detail,
        )
        return False

    try:
        restart_ollama_container_sync(container, c)
    except RuntimeError as exc:
        logger.error("ollama gpu recover failed: {}", exc)
        return False

    after = check_ollama_gpu_sync(c)
    record_snapshot(after, recovered=True)
    if after.gpu_ok:
        logger.info("ollama gpu recover succeeded for container {}", container)
        return True
    logger.error(
        "ollama gpu recover finished but check still failing ({}/{})",
        after.method,
        after.detail,
    )
    return False


def maybe_recover_after_slow_local_inference(
    *,
    elapsed_sec: float,
    provider_kind: str,
    cfg: Settings | None = None,
) -> None:
    c = cfg or settings
    if provider_kind != "local" or not ollama_gpu_guard_enabled(c):
        return
    if elapsed_sec < float(c.ollama_gpu_slow_task_sec):
        return
    if not recover_cooldown_elapsed(c):
        return
    logger.warning(
        "local llm task slow ({:.1f}s >= {}s); triggering ollama gpu recover",
        elapsed_sec,
        c.ollama_gpu_slow_task_sec,
    )
    ensure_ollama_gpu_ready_sync(fix=True, cfg=c)


def guard_loop() -> None:
    interval = max(60.0, float(settings.ollama_gpu_check_interval_sec))
    while not _bg_stop.wait(interval):
        try:
            ensure_ollama_gpu_ready_sync(cfg=settings)
        except Exception as exc:
            logger.warning("ollama gpu guard loop error: {}", exc)


def start_ollama_gpu_guard_background() -> None:
    global _bg_thread  # noqa: PLW0603
    if not ollama_gpu_guard_enabled():
        return
    if _bg_thread is not None and _bg_thread.is_alive():
        return
    _bg_stop.clear()
    _bg_thread = threading.Thread(target=guard_loop, name="ollama-gpu-guard", daemon=True)
    _bg_thread.start()


def stop_ollama_gpu_guard_background() -> None:
    _bg_stop.set()


def reset_ollama_gpu_guard_state_for_tests() -> None:
    global _last_check_monotonic, _last_recover_monotonic, _recover_count, _bg_thread  # noqa: PLW0603
    with _state_lock:
        _last_check_monotonic = 0.0
        _last_recover_monotonic = 0.0
        _recover_count = 0
        _last_snapshot.clear()
        _last_snapshot.update(
            {
                "enabled": False,
                "gpu_ok": None,
                "method": "skipped",
                "detail": "not_checked",
                "container": None,
                "auto_recover": False,
                "recover_count": 0,
                "last_check_at": None,
                "last_recover_at": None,
            }
        )
    _bg_stop.set()
    _bg_thread = None
