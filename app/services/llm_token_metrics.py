"""LLM token 累计统计（provider 返回 usage 时解析）。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

_STORE_VER = 1

_lock = threading.Lock()
_day_key = ""
_prompt_tokens = 0
_completion_tokens = 0
_by_task: dict[str, dict[str, int]] = {}


def today_key() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def rollover_if_needed() -> None:
    global _day_key, _prompt_tokens, _completion_tokens  # noqa: PLW0603
    today = today_key()
    if _day_key == today:
        return
    _day_key = today
    _prompt_tokens = 0
    _completion_tokens = 0
    _by_task.clear()


def stats_file_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "llm_token_stats.json"


def record_llm_token_usage(
    *,
    task: str | None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    prompt = max(0, int(prompt_tokens))
    completion = max(0, int(completion_tokens))
    if prompt == 0 and completion == 0:
        return
    task_key = str(task or "llm_chat").strip().lower() or "llm_chat"
    try:
        with _lock:
            rollover_if_needed()
            global _prompt_tokens, _completion_tokens  # noqa: PLW0603
            _prompt_tokens += prompt
            _completion_tokens += completion
            row = _by_task.setdefault(task_key, {"prompt_tokens": 0, "completion_tokens": 0})
            row["prompt_tokens"] += prompt
            row["completion_tokens"] += completion
    except Exception:
        pass


def load_stats_file() -> dict[str, Any]:
    path = stats_file_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def merge_llm_token_snapshots(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_task: dict[str, dict[str, int]] = {}
    prompt_tokens = 0
    completion_tokens = 0
    day_key = ""
    updated_at = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        day_key = str(row.get("day_key") or day_key)
        try:
            updated_at = max(updated_at, float(row.get("updated_at") or 0))
        except (TypeError, ValueError):
            pass
        prompt_tokens += int(row.get("prompt_tokens") or 0)
        completion_tokens += int(row.get("completion_tokens") or 0)
        src_by_task = row.get("by_task")
        if isinstance(src_by_task, dict):
            for task, metrics in src_by_task.items():
                if not isinstance(metrics, dict):
                    continue
                task_key = str(task).strip() or "llm_chat"
                dst = by_task.setdefault(task_key, {"prompt_tokens": 0, "completion_tokens": 0})
                dst["prompt_tokens"] += int(metrics.get("prompt_tokens") or 0)
                dst["completion_tokens"] += int(metrics.get("completion_tokens") or 0)
    return {
        "source": "ai",
        "day_key": day_key or today_key(),
        "updated_at": updated_at or time.time(),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "by_task": by_task,
    }


def _local_llm_token_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        rollover_if_needed()
        return {
            "source": "ai",
            "day_key": _day_key or today_key(),
            "updated_at": time.time(),
            "prompt_tokens": _prompt_tokens,
            "completion_tokens": _completion_tokens,
            "total_tokens": _prompt_tokens + _completion_tokens,
            "by_task": {task: dict(values) for task, values in _by_task.items()},
        }


def llm_token_metrics_snapshot(*, include_persisted: bool = True) -> dict[str, Any]:
    local = _local_llm_token_metrics_snapshot()
    if not include_persisted:
        return local
    persisted_raw = load_stats_file()
    if not isinstance(persisted_raw, dict) or not persisted_raw.get("day_key"):
        return local
    persisted = {
        "source": "ai",
        "day_key": str(persisted_raw.get("day_key") or ""),
        "updated_at": float(persisted_raw.get("updated_at") or 0),
        "prompt_tokens": int(persisted_raw.get("prompt_tokens") or 0),
        "completion_tokens": int(persisted_raw.get("completion_tokens") or 0),
        "total_tokens": int(persisted_raw.get("total_tokens") or 0),
        "by_task": persisted_raw.get("by_task") if isinstance(persisted_raw.get("by_task"), dict) else {},
    }
    local_has = local.get("total_tokens", 0) > 0 or bool(local.get("by_task"))
    if not local_has:
        return persisted
    return merge_llm_token_snapshots([persisted, local])


def flush_stats_sync() -> None:
    snapshot = llm_token_metrics_snapshot(include_persisted=True)
    if not snapshot.get("by_task") and snapshot.get("total_tokens", 0) == 0:
        return
    path = stats_file_path()
    payload = {"v": _STORE_VER, **snapshot}
    tmp = path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def clear_llm_token_metrics_for_tests() -> None:
    global _day_key, _prompt_tokens, _completion_tokens  # noqa: PLW0603
    with _lock:
        _day_key = ""
        _prompt_tokens = 0
        _completion_tokens = 0
        _by_task.clear()
