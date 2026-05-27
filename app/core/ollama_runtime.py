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

_RUNTIME_FILE = Path(settings.log_path) / "ollama_runtime.json"
_runtime_lock = Lock()
_ollama_proc: subprocess.Popen | None = None
_we_started_ollama = False
_PID_FILE = Path(settings.log_path) / "ollama_serve.pid"


def _read_runtime_file() -> dict:
    if not _RUNTIME_FILE.is_file():
        return {}
    try:
        return json.loads(_RUNTIME_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_runtime_file(data: dict) -> None:
    _RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    _RUNTIME_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def get_ollama_model() -> str:
    with _runtime_lock:
        model = _read_runtime_file().get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
        return settings.ollama_model


def set_ollama_model(model: str) -> str:
    name = model.strip()
    if not name:
        msg = "model name must not be empty"
        raise ValueError(msg)
    with _runtime_lock:
        data = _read_runtime_file()
        data["model"] = name
        _write_runtime_file(data)
    logger.info("ollama runtime model set to {}", name)
    return name


def reload_ollama_model_from_env() -> str:
    fresh = Settings()
    return set_ollama_model(fresh.ollama_model)


def ollama_base_url() -> str:
    return settings.ollama_url.rstrip("/")


def ollama_chat_url() -> str:
    return f"{ollama_base_url()}/api/chat"


def ollama_tags_url() -> str:
    return f"{ollama_base_url()}/api/tags"


def ollama_pull_url() -> str:
    return f"{ollama_base_url()}/api/pull"


async def ping_ollama(timeout: float = 2.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.get(ollama_tags_url())
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def ping_ollama_sync(timeout: float = 2.0) -> bool:
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            response = client.get(ollama_tags_url())
            return response.status_code == 200
    except httpx.HTTPError:
        return False


def _wait_until_ready_sync(timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ping_ollama_sync(timeout=2.0):
            return True
        time.sleep(1.0)
    return False


def _spawn_ollama_serve() -> None:
    global _ollama_proc, _we_started_ollama
    if _ollama_proc is not None and _ollama_proc.poll() is None:
        return

    parsed = urlparse(settings.ollama_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434
    env = os.environ.copy()
    if host not in ("127.0.0.1", "localhost", "0.0.0.0"):
        env["OLLAMA_HOST"] = f"http://{host}:{port}"

    cmd = [settings.ollama_binary, "serve"]
    logger.info("starting ollama subprocess: {}", " ".join(cmd))
    _ollama_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )
    _we_started_ollama = True
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(_ollama_proc.pid), encoding="utf-8")


def stop_ollama_if_started() -> None:
    global _ollama_proc, _we_started_ollama
    pid: int | None = None
    if _ollama_proc is not None and _ollama_proc.poll() is None:
        pid = _ollama_proc.pid
    elif _PID_FILE.is_file():
        try:
            pid = int(_PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None

    if pid is None:
        return

    try:
        os.kill(pid, signal.SIGTERM)
        logger.info("stopped ollama subprocess pid={}", pid)
    except ProcessLookupError:
        pass
    finally:
        _PID_FILE.unlink(missing_ok=True)
        _ollama_proc = None
        _we_started_ollama = False


def ensure_ollama_ready_sync() -> None:
    if not settings.ollama_enable:
        return
    if ping_ollama_sync():
        logger.info("ollama already reachable at {}", settings.ollama_url)
        return
    if not settings.ollama_auto_start:
        logger.warning("ollama unreachable at {} and OLLAMA_AUTO_START is false", settings.ollama_url)
        return

    _spawn_ollama_serve()
    if not _wait_until_ready_sync(settings.ollama_startup_timeout):
        logger.error("ollama subprocess did not become ready within {}s", settings.ollama_startup_timeout)
        return
    logger.info("ollama subprocess is ready at {}", settings.ollama_url)

    if settings.ollama_auto_pull:
        model = get_ollama_model()
        try:
            pull_ollama_model_sync(model)
        except Exception as e:
            logger.warning("ollama auto pull failed for {}: {}", model, e)


async def ensure_ollama_ready() -> None:
    await asyncio.to_thread(ensure_ollama_ready_sync)


def pull_ollama_model_sync(model: str, timeout: float = 600.0) -> None:
    name = model.strip()
    if not name:
        return
    logger.info("ollama pulling model {}", name)
    with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
        with client.stream("POST", ollama_pull_url(), json={"name": name}) as response:
            response.raise_for_status()
            for _line in response.iter_lines():
                pass
    logger.info("ollama pull finished for {}", name)


async def pull_ollama_model(model: str) -> None:
    await asyncio.to_thread(pull_ollama_model_sync, model)


async def switch_ollama_model(model: str, *, pull: bool = True) -> str:
    name = set_ollama_model(model)
    if pull:
        await pull_ollama_model(name)
    return name
