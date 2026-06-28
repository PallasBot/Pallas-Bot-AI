from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

import httpx

from app.core.config import Settings, settings
from app.core.logger import logger

_RUNTIME_FILE = Path(settings.log_path) / "llm_runtime.json"
_LEGACY_RUNTIME_FILE = Path(settings.log_path) / "ollama_runtime.json"
_runtime_lock = Lock()
_backend_proc: subprocess.Popen | None = None
_we_started_backend = False
_PID_FILE = Path(settings.log_path) / "llm_backend_serve.pid"
_LEGACY_PID_FILE = Path(settings.log_path) / "ollama_serve.pid"


def _read_runtime_file() -> dict:
    for path in (_RUNTIME_FILE, _LEGACY_RUNTIME_FILE):
        if not path.is_file():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def _write_runtime_file(data: dict) -> None:
    _RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    _RUNTIME_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def get_llm_model() -> str:
    with _runtime_lock:
        model = _read_runtime_file().get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
        return settings.llm_model


def get_llm_num_gpu() -> int | None:
    with _runtime_lock:
        data = _read_runtime_file()
        value = data.get("num_gpu")
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return settings.llm_num_gpu


def set_llm_model(model: str) -> str:
    name = model.strip()
    if not name:
        msg = "model name must not be empty"
        raise ValueError(msg)
    with _runtime_lock:
        data = _read_runtime_file()
        data["model"] = name
        _write_runtime_file(data)
    logger.info("llm runtime model set to {}", name)
    return name


def set_llm_num_gpu(value: int | None) -> int | None:
    normalized = int(value) if value is not None else None
    with _runtime_lock:
        data = _read_runtime_file()
        old = data.get("num_gpu")
        if normalized is None:
            data.pop("num_gpu", None)
        else:
            data["num_gpu"] = normalized
        if old != normalized:
            data["gpu_config_dirty"] = True
        _write_runtime_file(data)
    logger.info("llm runtime num_gpu set to {}", normalized)
    return normalized


def mark_llm_gpu_config_dirty() -> None:
    with _runtime_lock:
        data = _read_runtime_file()
        data["gpu_config_dirty"] = True
        _write_runtime_file(data)


def clear_llm_gpu_config_dirty() -> None:
    with _runtime_lock:
        data = _read_runtime_file()
        data["gpu_config_dirty"] = False
        _write_runtime_file(data)


def is_llm_gpu_config_dirty() -> bool:
    with _runtime_lock:
        return bool(_read_runtime_file().get("gpu_config_dirty"))


def reload_llm_runtime_from_env() -> tuple[str, int | None]:
    fresh = Settings()
    model = set_llm_model(fresh.llm_model)
    num_gpu = set_llm_num_gpu(fresh.llm_num_gpu)
    return model, num_gpu


def reload_llm_model_from_env() -> str:
    model, _ = reload_llm_runtime_from_env()
    return model


def local_backend_base_url() -> str:
    return settings.llm_backend_url.rstrip("/")


def local_backend_chat_url() -> str:
    return f"{local_backend_base_url()}/api/chat"


def local_backend_generate_url() -> str:
    return f"{local_backend_base_url()}/api/generate"


def local_backend_tags_url() -> str:
    return f"{local_backend_base_url()}/api/tags"


def local_backend_pull_url() -> str:
    return f"{local_backend_base_url()}/api/pull"


async def ping_local_backend(timeout_sec: float = 2.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
            response = await client.get(local_backend_tags_url())
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def ping_local_backend_sync(timeout_sec: float = 2.0) -> bool:
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout_sec)) as client:
            response = client.get(local_backend_tags_url())
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def wait_local_backend_ready_sync(timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ping_local_backend_sync(timeout=2.0):
            return True
        time.sleep(1.0)
    return False


def spawn_local_backend_process() -> None:
    global _backend_proc, _we_started_backend
    if _backend_proc is not None and _backend_proc.poll() is None:
        return

    parsed = urlparse(settings.llm_backend_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434
    env = os.environ.copy()
    if host not in ("127.0.0.1", "localhost", "0.0.0.0"):
        env["OLLAMA_HOST"] = f"http://{host}:{port}"

    cmd = [settings.llm_backend_binary, "serve"]
    logger.info("starting local llm backend subprocess: {}", " ".join(cmd))
    _backend_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    _we_started_backend = True
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(_backend_proc.pid), encoding="utf-8")


def stop_local_backend_if_started() -> None:
    global _backend_proc, _we_started_backend
    pid: int | None = None
    if _backend_proc is not None and _backend_proc.poll() is None:
        pid = _backend_proc.pid
    elif _PID_FILE.is_file():
        try:
            pid = int(_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None
    elif _LEGACY_PID_FILE.is_file():
        try:
            pid = int(_LEGACY_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None

    if pid is None:
        return

    try:
        os.kill(pid, signal.SIGTERM)
        logger.info("stopped local llm backend subprocess pid={}", pid)
    except ProcessLookupError:
        pass
    finally:
        _PID_FILE.unlink(missing_ok=True)
        _LEGACY_PID_FILE.unlink(missing_ok=True)
        _backend_proc = None
        _we_started_backend = False


def ensure_local_backend_ready_sync() -> None:
    if not settings.llm_chat_enabled:
        return
    if ping_local_backend_sync():
        logger.info("local llm backend already reachable at {}", settings.llm_backend_url)
        return
    if not settings.llm_auto_start:
        logger.warning(
            "local llm backend unreachable at {} and LLM_AUTO_START is false",
            settings.llm_backend_url,
        )
        return

    spawn_local_backend_process()
    if not wait_local_backend_ready_sync(settings.llm_startup_timeout):
        logger.error(
            "local llm backend subprocess did not become ready within {}s",
            settings.llm_startup_timeout,
        )
        return
    logger.info("local llm backend subprocess is ready at {}", settings.llm_backend_url)

    if settings.llm_auto_pull:
        model = get_llm_model()
        try:
            pull_local_backend_model_sync(model)
        except Exception as e:
            logger.warning("local llm backend auto pull failed for {}: {}", model, e)


async def ensure_local_backend_ready() -> None:
    await asyncio.to_thread(ensure_local_backend_ready_sync)


def pull_local_backend_model_sync(model: str, timeout: float = 600.0) -> None:
    name = model.strip()
    if not name:
        return
    logger.info("local llm backend pulling model {}", name)
    with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
        with client.stream("POST", local_backend_pull_url(), json={"name": name}) as response:
            response.raise_for_status()
            for _line in response.iter_lines():
                pass
    logger.info("local llm backend pull finished for {}", name)


async def pull_local_backend_model(model: str) -> None:
    await asyncio.to_thread(pull_local_backend_model_sync, model)


def unload_resident_backend_model_sync(model: str | None = None) -> tuple[int, str]:
    target = (model or "").strip() or get_llm_model()
    if not target:
        return 200, ""
    logger.info("llm backend unload sync: model={}", target)
    payload = {
        "model": target,
        "keep_alive": 0,
    }
    timeout = httpx.Timeout(settings.llm_request_timeout)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(local_backend_generate_url(), json=payload)
        return response.status_code, response.text


async def unload_resident_backend_model(model: str | None = None) -> tuple[int, str]:
    return await asyncio.to_thread(unload_resident_backend_model_sync, model)


def prepare_local_backend_for_worker_sync() -> None:
    ensure_local_backend_ready_sync()
    if not settings.llm_chat_enabled:
        return
    status, body = unload_resident_backend_model_sync()
    if status != 200:
        logger.warning("后台任务卸载过期模型返回 {} {}", status, body)
    mark_llm_gpu_config_dirty()
    logger.info(
        "后台任务已就绪本地 LLM：model={} num_gpu={}",
        get_llm_model(),
        get_llm_num_gpu(),
    )


async def switch_llm_model(model: str, *, pull: bool = True, unload: bool = True) -> str:
    if unload:
        try:
            status, body = await unload_resident_backend_model()
            if status != 200:
                logger.warning("llm switch: unload before switch returned {} {}", status, body)
        except httpx.HTTPError as exc:
            logger.warning("llm switch: unload before switch failed: {}", exc)
    name = set_llm_model(model)
    mark_llm_gpu_config_dirty()
    if pull:
        await pull_local_backend_model(name)
    return name


async def switch_llm_num_gpu(num_gpu: int, *, unload: bool = True) -> int:
    if num_gpu < 0:
        msg = "num_gpu must be >= 0"
        raise ValueError(msg)
    if unload:
        try:
            status, body = await unload_resident_backend_model()
            if status != 200:
                logger.warning("llm num_gpu switch: unload returned {} {}", status, body)
        except httpx.HTTPError as exc:
            logger.warning("llm num_gpu switch: unload failed: {}", exc)
    return set_llm_num_gpu(num_gpu) or num_gpu
