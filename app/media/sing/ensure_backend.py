"""按需拉取 DDSP-SVC 多版本检出（git clone / submodule）。

触发条件应是「明确要用」某 backend（如 preferred_backend=ddsp_6.3），
而不是 fallback 链上每一个都自动下——每份约 1.6G。
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path  # noqa: TC003
from typing import Any

from app.core.logger import logger
from app.media.assets import repo_root

DDSP_REPO_URL = "https://github.com/PallasBot/DDSP-SVC.git"

# backend_id → 相对仓根目录 + 分支。与 resource/sing/registry.yaml 对齐。
DDSP_BACKEND_SPECS: dict[str, dict[str, str]] = {
    "ddsp_6.3": {"rel": "app/workers/sing/DDSP-SVC-6.3", "branch": "6.3"},
    "ddsp_6.2": {"rel": "app/workers/sing/DDSP-SVC", "branch": "6.2"},
    "ddsp_6.1": {"rel": "app/workers/sing/DDSP-SVC-6.1", "branch": "6.1"},
}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_jobs_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def auto_installable_backend_ids() -> frozenset[str]:
    return frozenset(DDSP_BACKEND_SPECS)


def backend_checkout_path(backend_id: str, *, root: Path | None = None) -> Path | None:
    spec = DDSP_BACKEND_SPECS.get(backend_id)
    if spec is None:
        return None
    return repo_root(root) / spec["rel"]


def backend_script_present(backend_id: str, *, root: Path | None = None) -> bool:
    base = backend_checkout_path(backend_id, root=root)
    if base is None:
        return False
    return (base / "main_reflow.py").is_file()


def describe_backend_install(backend_id: str, *, root: Path | None = None) -> dict[str, Any]:
    spec = DDSP_BACKEND_SPECS.get(backend_id)
    present = backend_script_present(backend_id, root=root)
    return {
        "id": backend_id,
        "auto_installable": spec is not None,
        "script_present": present,
        "path": None if spec is None else spec["rel"],
        "branch": None if spec is None else spec["branch"],
    }


def _lock_for(backend_id: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(backend_id)
        if lock is None:
            lock = threading.Lock()
            _locks[backend_id] = lock
        return lock


def _run_git(args: list[str], *, cwd: Path | None = None, timeout: float = 600.0) -> tuple[int, str]:
    try:
        completed = subprocess.run(  # noqa: S603
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return 1, "未找到 git，无法自动拉取 DDSP-SVC"
    except subprocess.TimeoutExpired:
        return 1, f"git {' '.join(args)} 超时（{timeout:.0f}s）"
    out = ((completed.stdout or "") + (completed.stderr or "")).strip()
    return int(completed.returncode), out[-4000:]


def _try_submodule_init(root: Path, rel: str) -> tuple[bool, str]:
    gitmodules = root / ".gitmodules"
    if not gitmodules.is_file():
        return False, "无 .gitmodules"
    code, out = _run_git(["submodule", "update", "--init", "--", rel], cwd=root, timeout=600.0)
    if code != 0:
        return False, out or f"submodule update 退出码 {code}"
    return True, out or "submodule ok"


def _clone_branch(root: Path, rel: str, branch: str) -> tuple[bool, str]:
    dest = root / rel
    if dest.exists() and any(dest.iterdir()):
        return False, f"目标目录非空且缺少 main_reflow.py: {rel}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            dest.rmdir()
        except OSError:
            return False, f"无法清理空目录: {rel}"
    code, out = _run_git(
        ["clone", "--depth", "1", "--branch", branch, DDSP_REPO_URL, str(dest)],
        cwd=root,
        timeout=900.0,
    )
    if code != 0:
        return False, out or f"git clone 退出码 {code}"
    return True, out or "clone ok"


def ensure_svc_backend(
    backend_id: str,
    *,
    root: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """同步确保 backend 脚本在盘。已存在则直接返回。"""
    spec = DDSP_BACKEND_SPECS.get(backend_id)
    if spec is None:
        return {
            "ok": False,
            "backend_id": backend_id,
            "status": "unsupported",
            "error": f"backend {backend_id} 不支持自动安装（仅 DDSP 6.1/6.2/6.3）",
        }
    base = repo_root(root)
    rel = spec["rel"]
    branch = spec["branch"]
    script = base / rel / "main_reflow.py"
    if script.is_file() and not force:
        return {
            "ok": True,
            "backend_id": backend_id,
            "status": "present",
            "path": rel,
            "branch": branch,
            "error": None,
        }

    lock = _lock_for(backend_id)
    if not lock.acquire(blocking=False):
        return {
            "ok": False,
            "backend_id": backend_id,
            "status": "busy",
            "path": rel,
            "branch": branch,
            "error": "正在拉取同一 backend，请稍后重试",
        }
    try:
        if script.is_file() and not force:
            return {
                "ok": True,
                "backend_id": backend_id,
                "status": "present",
                "path": rel,
                "branch": branch,
                "error": None,
            }
        logger.info("svc backend ensure start: id={} path={} branch={}", backend_id, rel, branch)
        ok, detail = _try_submodule_init(base, rel)
        if not ok or not script.is_file():
            ok, detail = _clone_branch(base, rel, branch)
        if not script.is_file():
            logger.error("svc backend ensure failed: id={} detail={}", backend_id, detail)
            return {
                "ok": False,
                "backend_id": backend_id,
                "status": "failed",
                "path": rel,
                "branch": branch,
                "error": detail or "拉取后仍缺少 main_reflow.py",
            }
        logger.info("svc backend ensure ok: id={} path={}", backend_id, rel)
        return {
            "ok": True,
            "backend_id": backend_id,
            "status": "installed",
            "path": rel,
            "branch": branch,
            "error": None,
            "detail": detail[-500:] if detail else None,
        }
    finally:
        lock.release()


def ensure_svc_backend_if_needed(backend_id: str, *, root: Path | None = None) -> dict[str, Any] | None:
    """仅当 backend 可自动安装且脚本缺失时执行 ensure；否则返回 None（无需动作）。"""
    backend_id = (backend_id or "").strip()
    if not backend_id or backend_id not in DDSP_BACKEND_SPECS:
        return None
    if backend_script_present(backend_id, root=root):
        return {
            "ok": True,
            "backend_id": backend_id,
            "status": "present",
            "path": DDSP_BACKEND_SPECS[backend_id]["rel"],
            "branch": DDSP_BACKEND_SPECS[backend_id]["branch"],
            "error": None,
        }
    return ensure_svc_backend(backend_id, root=root)


def schedule_ensure_svc_backend(backend_id: str, *, root: Path | None = None) -> dict[str, Any]:
    """后台拉取；给 WebUI 保存 preferred 时用，避免卡住 HTTP。"""
    backend_id = (backend_id or "").strip()
    if not backend_id:
        return {"ok": True, "status": "skipped", "backend_id": backend_id}
    if backend_id not in DDSP_BACKEND_SPECS:
        return {"ok": True, "status": "unsupported", "backend_id": backend_id}
    if backend_script_present(backend_id, root=root):
        return {
            "ok": True,
            "status": "present",
            "backend_id": backend_id,
            "path": DDSP_BACKEND_SPECS[backend_id]["rel"],
        }
    base = repo_root(root)

    def _worker() -> None:
        result = ensure_svc_backend(backend_id, root=base)
        with _jobs_lock:
            _jobs[backend_id] = {**result, "finished": True}

    with _jobs_lock:
        prev = _jobs.get(backend_id)
        if prev and not prev.get("finished") and prev.get("status") == "running":
            return {"ok": True, "status": "busy", "backend_id": backend_id}
        _jobs[backend_id] = {"ok": True, "status": "running", "backend_id": backend_id, "finished": False}

    threading.Thread(target=_worker, name=f"ensure-svc-{backend_id}", daemon=True).start()
    return {
        "ok": True,
        "status": "started",
        "backend_id": backend_id,
        "path": DDSP_BACKEND_SPECS[backend_id]["rel"],
        "branch": DDSP_BACKEND_SPECS[backend_id]["branch"],
        "message": f"正在后台拉取 {backend_id}（约 1.6G），完成后即可推理",
    }


def ensure_job_status(backend_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(backend_id)
        return dict(job) if job else None
