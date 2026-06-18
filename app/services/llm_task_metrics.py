"""LLM 任务计数：热路径仅内存自增，落盘由后台定时任务完成。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from app.providers.router import infer_task

_STORE_VER = 1
_TASKS = frozenset({"llm_chat", "repeater_polish", "repeater_polish_lite", "repeater_fallback", "repeater_select", "drunk"})
_EVENTS = frozenset({"task_ok", "task_fail"})
_CLASSIFY_METRICS = frozenset({
    "tier_simple",
    "tier_medium",
    "tier_complex",
    "tools_on",
    "tools_off",
    "vision_on",
    "vision_off",
})

_lock = threading.Lock()
_day_key = ""
_counters: dict[str, int] = {}
_flush_thread: threading.Thread | None = None
_flush_stop = threading.Event()


def normalize_llm_task_name(raw: str | None) -> str:
    task = str(raw or "").strip().lower()
    if task in _TASKS:
        return task
    if task:
        return "other"
    return "llm_chat"


def stats_file_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "llm_task_stats.json"


def today_key() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def rollover_if_needed() -> None:
    global _day_key  # noqa: PLW0603
    today = today_key()
    if _day_key == today:
        return
    _day_key = today
    _counters.clear()


def record_ai_llm_task(task: str | None, event: str) -> None:
    if event not in _EVENTS:
        return
    key = normalize_llm_task_name(task)
    try:
        with _lock:
            rollover_if_needed()
            _counters[f"{key}:{event}"] = int(_counters.get(f"{key}:{event}", 0)) + 1
    except Exception:
        pass


def record_ai_llm_task_from_metadata(metadata: dict[str, Any] | None, event: str) -> None:
    meta = metadata if isinstance(metadata, dict) else {}
    record_ai_llm_task(infer_task(meta), event)


def record_ai_llm_classification(metadata: dict[str, Any] | None) -> None:
    meta = metadata if isinstance(metadata, dict) else {}
    cls = meta.get("classification")
    if not isinstance(cls, dict):
        return
    task = normalize_llm_task_name(infer_task(meta))
    tier = str(cls.get("tier") or "medium").strip().lower()
    if tier not in ("simple", "medium", "complex"):
        tier = "medium"
    tier_metric = f"tier_{tier}"
    tools_metric = "tools_on" if bool(cls.get("needs_tools")) else "tools_off"
    vision_metric = "vision_on" if bool(cls.get("needs_vision")) else "vision_off"
    try:
        with _lock:
            rollover_if_needed()
            for metric in (tier_metric, tools_metric, vision_metric):
                if metric not in _CLASSIFY_METRICS:
                    continue
                key = f"{task}:{metric}"
                _counters[key] = int(_counters.get(key, 0)) + 1
    except Exception:
        pass


def _snapshot_from_persisted_payload(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    day_key = str(raw.get("day_key") or "").strip()
    if len(day_key) < 10:
        return {}
    out: dict[str, Any] = {
        "source": str(raw.get("source") or "ai"),
        "day_key": day_key,
        "updated_at": float(raw.get("updated_at") or 0),
        "by_task": raw.get("by_task") if isinstance(raw.get("by_task"), dict) else {},
        "totals": raw.get("totals") if isinstance(raw.get("totals"), dict) else {},
    }
    cls = raw.get("classification")
    if isinstance(cls, dict):
        out["classification"] = cls
    return out


def merge_llm_task_snapshots(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_task: dict[str, dict[str, int]] = {}
    totals = {"task_ok": 0, "task_fail": 0}
    classify_totals = dict.fromkeys(_CLASSIFY_METRICS, 0)
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
        src_by_task = row.get("by_task")
        if isinstance(src_by_task, dict):
            for task, metrics in src_by_task.items():
                if not isinstance(metrics, dict):
                    continue
                task_key = str(task).strip() or "llm_chat"
                dst = by_task.setdefault(task_key, {"task_ok": 0, "task_fail": 0})
                for metric in _EVENTS:
                    dst[metric] = int(dst.get(metric) or 0) + int(metrics.get(metric) or 0)
                for metric in _CLASSIFY_METRICS:
                    if metric in metrics:
                        dst[metric] = int(dst.get(metric) or 0) + int(metrics.get(metric) or 0)
                        classify_totals[metric] += int(metrics.get(metric) or 0)
        src_totals = row.get("totals")
        if isinstance(src_totals, dict):
            for metric in _EVENTS:
                totals[metric] += int(src_totals.get(metric) or 0)
        cls = row.get("classification")
        if isinstance(cls, dict):
            cls_totals = cls.get("totals")
            if isinstance(cls_totals, dict):
                for metric in _CLASSIFY_METRICS:
                    classify_totals[metric] += int(cls_totals.get(metric) or 0)
    if not totals["task_ok"] and not totals["task_fail"]:
        for metrics in by_task.values():
            totals["task_ok"] += int(metrics.get("task_ok") or 0)
            totals["task_fail"] += int(metrics.get("task_fail") or 0)
    return {
        "source": "ai",
        "day_key": day_key or today_key(),
        "updated_at": updated_at or time.time(),
        "by_task": by_task,
        "totals": totals,
        "classification": {"totals": classify_totals},
    }


def _local_llm_task_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        rollover_if_needed()
        by_task: dict[str, dict[str, int]] = {}
        totals = {"task_ok": 0, "task_fail": 0}
        classify_totals = dict.fromkeys(_CLASSIFY_METRICS, 0)
        for compound, value in _counters.items():
            if ":" not in compound:
                continue
            task, metric = compound.split(":", 1)
            count = int(value)
            if metric in _EVENTS:
                row = by_task.setdefault(task, {"task_ok": 0, "task_fail": 0})
                row[metric] = count
                totals[metric] += count
            elif metric in _CLASSIFY_METRICS:
                row = by_task.setdefault(task, {"task_ok": 0, "task_fail": 0})
                row[metric] = count
                classify_totals[metric] += count
        return {
            "source": "ai",
            "day_key": _day_key or today_key(),
            "updated_at": time.time(),
            "by_task": by_task,
            "totals": totals,
            "classification": {
                "totals": classify_totals,
            },
        }


def llm_task_metrics_snapshot(*, include_persisted: bool = True) -> dict[str, Any]:
    local = _local_llm_task_metrics_snapshot()
    if not include_persisted:
        return local
    persisted = _snapshot_from_persisted_payload(load_stats_file())
    if not persisted:
        return local
    local_has = bool(local.get("by_task")) or any((local.get("totals") or {}).values())
    if not local_has:
        return persisted
    return merge_llm_task_snapshots([persisted, local])


def load_stats_file() -> dict[str, Any]:
    path = stats_file_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def flush_stats_sync() -> None:
    snapshot = llm_task_metrics_snapshot(include_persisted=True)
    has_task = bool(snapshot.get("by_task")) or any((snapshot.get("totals") or {}).values())
    if has_task:
        path = stats_file_path()
        payload = {"v": _STORE_VER, **snapshot}
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass
    try:
        from app.services.llm_token_metrics import flush_stats_sync as flush_token_stats_sync

        flush_token_stats_sync()
    except Exception:
        pass


def flush_loop() -> None:
    while not _flush_stop.wait(120.0):
        try:
            flush_stats_sync()
        except Exception:
            pass


def start_background_flush() -> None:
    global _flush_thread  # noqa: PLW0603
    if _flush_thread is not None and _flush_thread.is_alive():
        return
    _flush_stop.clear()
    _flush_thread = threading.Thread(target=flush_loop, name="llm-task-metrics-flush", daemon=True)
    _flush_thread.start()


def stop_background_flush() -> None:
    _flush_stop.set()
    try:
        flush_stats_sync()
    except Exception:
        pass


def clear_llm_task_metrics_for_tests() -> None:
    global _day_key, _flush_thread  # noqa: PLW0603
    with _lock:
        _day_key = ""
        _counters.clear()
    _flush_stop.set()
    _flush_thread = None
