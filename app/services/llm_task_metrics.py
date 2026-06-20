"""LLM 任务计数：热路径仅内存自增，落盘由后台定时任务完成。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from app.services.llm_token_metrics import flush_stats_sync as flush_token_stats_sync


def infer_task(meta: dict[str, Any]) -> str:
    # 延迟 import：app.providers.router 依赖本模块，模块顶层 import 会形成循环
    # （chain.py -> llm_task_metrics -> router -> ... -> chain），导致 media worker 初始化 chat 任务时 ImportError。
    from app.providers.router import infer_task as _infer_task

    return _infer_task(meta)


_STORE_VER = 1
_TASKS = frozenset({
    "llm_chat",
    "repeater_polish",
    "repeater_polish_lite",
    "repeater_fallback",
    "repeater_select",
    "drunk",
})
_EVENTS = frozenset({"task_ok", "task_fail"})
_SHAPING_METRICS = frozenset({
    "variation_applied",
    "rewrite_trim_servicey_phrase",
    "rewrite_avoid_repeated_opener",
    "rewrite_trim_overexplaining",
    "rewrite_adapt_llm_chat_length",
    "rewrite_soften_template_ending",
})
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
_task_states: dict[str, tuple[str, str]] = {}
_failure_counts: dict[str, int] = {}
_provider_stats: dict[str, dict[str, Any]] = {}
_model_stats: dict[str, dict[str, Any]] = {}
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
    _task_states.clear()
    _failure_counts.clear()
    _provider_stats.clear()
    _model_stats.clear()


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


def record_ai_llm_task_state(task_id: str, task: str | None, state: str) -> None:
    if state not in {"queued", "running"}:
        return
    key = str(task_id or "").strip()
    if not key:
        return
    task_name = normalize_llm_task_name(task)
    try:
        with _lock:
            rollover_if_needed()
            _task_states[key] = (task_name, state)
    except Exception:
        pass


def clear_ai_llm_task_state(task_id: str) -> None:
    key = str(task_id or "").strip()
    if not key:
        return
    try:
        with _lock:
            _task_states.pop(key, None)
    except Exception:
        pass


def record_ai_llm_failure(failure_class: str | None) -> None:
    key = str(failure_class or "").strip().lower()
    if not key:
        return
    try:
        with _lock:
            rollover_if_needed()
            _failure_counts[key] = int(_failure_counts.get(key) or 0) + 1
    except Exception:
        pass


def _record_dimension_result(
    store: dict[str, dict[str, Any]],
    key: str,
    *,
    succeeded: bool,
    latency_ms: int | None,
    failure_class: str | None,
) -> None:
    row = store.setdefault(
        key,
        {
            "requests": 0,
            "succeeded": 0,
            "failed": 0,
            "total_latency_ms": 0,
            "recent_failure_class": None,
        },
    )
    row["requests"] = int(row.get("requests") or 0) + 1
    if succeeded:
        row["succeeded"] = int(row.get("succeeded") or 0) + 1
        if not failure_class:
            row["recent_failure_class"] = None
    else:
        row["failed"] = int(row.get("failed") or 0) + 1
        if failure_class:
            row["recent_failure_class"] = failure_class
    if latency_ms is not None:
        row["total_latency_ms"] = int(row.get("total_latency_ms") or 0) + max(0, int(latency_ms))


def record_ai_llm_provider_result(
    *,
    task: str | None,
    provider: str | None,
    model: str | None,
    succeeded: bool,
    latency_ms: int | None = None,
    failure_class: str | None = None,
) -> None:
    provider_key = str(provider or "").strip().lower()
    model_key = str(model or "").strip()
    failure_key = str(failure_class or "").strip().lower() or None
    try:
        with _lock:
            rollover_if_needed()
            if provider_key:
                _record_dimension_result(
                    _provider_stats,
                    provider_key,
                    succeeded=succeeded,
                    latency_ms=latency_ms,
                    failure_class=failure_key,
                )
            if model_key:
                _record_dimension_result(
                    _model_stats,
                    model_key,
                    succeeded=succeeded,
                    latency_ms=latency_ms,
                    failure_class=failure_key,
                )
            if failure_key:
                _failure_counts[failure_key] = int(_failure_counts.get(failure_key) or 0) + 1
    except Exception:
        pass


def record_ai_llm_task_from_metadata(metadata: dict[str, Any] | None, event: str) -> None:
    meta = metadata if isinstance(metadata, dict) else {}
    record_ai_llm_task(infer_task(meta), event)


def record_ai_llm_shaping(metadata: dict[str, Any] | None) -> None:
    meta = metadata if isinstance(metadata, dict) else {}
    task = normalize_llm_task_name(infer_task(meta))
    metrics: list[str] = []
    if bool(meta.get("variation_applied")):
        metrics.append("variation_applied")
    applied_rules = meta.get("rewrite_applied_rules")
    if isinstance(applied_rules, (list, tuple, set)):
        for raw in applied_rules:
            rule = str(raw or "").strip().lower()
            if not rule:
                continue
            metric = f"rewrite_{rule}"
            if metric in _SHAPING_METRICS:
                metrics.append(metric)
    if not metrics:
        return
    try:
        with _lock:
            rollover_if_needed()
            for metric in dict.fromkeys(metrics):
                key = f"{task}:{metric}"
                _counters[key] = int(_counters.get(key, 0)) + 1
    except Exception:
        pass


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
    shaping = raw.get("shaping")
    if isinstance(shaping, dict):
        shaping_totals = shaping.get("totals")
        if isinstance(shaping_totals, dict):
            out["shaping"] = {"totals": dict(shaping_totals)}
    cls = raw.get("classification")
    if isinstance(cls, dict):
        out["classification"] = cls
    return out


def merge_llm_task_snapshots(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_task: dict[str, dict[str, int]] = {}
    totals = {"task_ok": 0, "task_fail": 0}
    state_counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
    shaping_totals = dict.fromkeys(_SHAPING_METRICS, 0)
    classify_totals = dict.fromkeys(_CLASSIFY_METRICS, 0)
    failure_counts: dict[str, int] = {}
    provider_stats: dict[str, dict[str, Any]] = {}
    model_stats: dict[str, dict[str, Any]] = {}
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
                dst = by_task.setdefault(task_key, {"queued": 0, "running": 0, "task_ok": 0, "task_fail": 0})
                for metric in ("queued", "running"):
                    dst[metric] = int(dst.get(metric) or 0) + int(metrics.get(metric) or 0)
                    state_counts[metric] += int(metrics.get(metric) or 0)
                for metric in _EVENTS:
                    dst[metric] = int(dst.get(metric) or 0) + int(metrics.get(metric) or 0)
                for metric in _SHAPING_METRICS:
                    if metric in metrics:
                        dst[metric] = int(dst.get(metric) or 0) + int(metrics.get(metric) or 0)
                for metric in _CLASSIFY_METRICS:
                    if metric in metrics:
                        dst[metric] = int(dst.get(metric) or 0) + int(metrics.get(metric) or 0)
        src_totals = row.get("totals")
        if isinstance(src_totals, dict):
            for metric in _EVENTS:
                totals[metric] += int(src_totals.get(metric) or 0)
        shaping = row.get("shaping")
        if isinstance(shaping, dict):
            shaping_totals_row = shaping.get("totals")
            if isinstance(shaping_totals_row, dict):
                for metric in _SHAPING_METRICS:
                    shaping_totals[metric] += int(shaping_totals_row.get(metric) or 0)
        src_failures = row.get("failure_counts")
        if isinstance(src_failures, dict):
            for failure_class, count in src_failures.items():
                failure_key = str(failure_class).strip().lower()
                if not failure_key:
                    continue
                failure_counts[failure_key] = int(failure_counts.get(failure_key) or 0) + int(count or 0)
        for field_name, dest in (("provider_stats", provider_stats), ("model_stats", model_stats)):
            src_stats = row.get(field_name)
            if not isinstance(src_stats, dict):
                continue
            for stat_key, metrics in src_stats.items():
                if not isinstance(metrics, dict):
                    continue
                key = str(stat_key).strip()
                if not key:
                    continue
                dst = dest.setdefault(
                    key,
                    {
                        "requests": 0,
                        "succeeded": 0,
                        "failed": 0,
                        "total_latency_ms": 0,
                        "recent_failure_class": None,
                    },
                )
                for metric in ("requests", "succeeded", "failed", "total_latency_ms"):
                    dst[metric] = int(dst.get(metric) or 0) + int(metrics.get(metric) or 0)
                recent_failure = metrics.get("recent_failure_class")
                if recent_failure:
                    dst["recent_failure_class"] = str(recent_failure)
        cls = row.get("classification")
        if isinstance(cls, dict):
            cls_totals = cls.get("totals")
            if isinstance(cls_totals, dict):
                for metric in _CLASSIFY_METRICS:
                    classify_totals[metric] += int(cls_totals.get(metric) or 0)
    if not any(shaping_totals.values()):
        for metrics in by_task.values():
            for metric in _SHAPING_METRICS:
                shaping_totals[metric] += int(metrics.get(metric) or 0)
    if not any(classify_totals.values()):
        for metrics in by_task.values():
            for metric in _CLASSIFY_METRICS:
                classify_totals[metric] += int(metrics.get(metric) or 0)
    if not totals["task_ok"] and not totals["task_fail"]:
        for metrics in by_task.values():
            totals["task_ok"] += int(metrics.get("task_ok") or 0)
            totals["task_fail"] += int(metrics.get("task_fail") or 0)
    state_counts["succeeded"] = int(totals["task_ok"] or 0)
    state_counts["failed"] = int(totals["task_fail"] or 0)
    for stats in (provider_stats, model_stats):
        for row in stats.values():
            requests = int(row.get("requests") or 0)
            total_latency = int(row.get("total_latency_ms") or 0)
            row["avg_latency_ms"] = int(total_latency / requests) if requests > 0 else None
    return {
        "source": "ai",
        "day_key": day_key or today_key(),
        "updated_at": updated_at or time.time(),
        "by_task": by_task,
        "totals": totals,
        "state_counts": state_counts,
        "failure_counts": failure_counts,
        "provider_stats": provider_stats,
        "model_stats": model_stats,
        "shaping": {"totals": shaping_totals},
        "classification": {"totals": classify_totals},
    }


def _local_llm_task_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        rollover_if_needed()
        by_task: dict[str, dict[str, int]] = {}
        totals = {"task_ok": 0, "task_fail": 0}
        state_counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
        shaping_totals = dict.fromkeys(_SHAPING_METRICS, 0)
        classify_totals = dict.fromkeys(_CLASSIFY_METRICS, 0)
        provider_stats = {key: dict(value) for key, value in _provider_stats.items()}
        model_stats = {key: dict(value) for key, value in _model_stats.items()}
        for task, state in _task_states.values():
            row = by_task.setdefault(task, {"queued": 0, "running": 0, "task_ok": 0, "task_fail": 0})
            row[state] = int(row.get(state) or 0) + 1
            state_counts[state] += 1
        for compound, value in _counters.items():
            if ":" not in compound:
                continue
            task, metric = compound.split(":", 1)
            count = int(value)
            if metric in _EVENTS:
                row = by_task.setdefault(task, {"queued": 0, "running": 0, "task_ok": 0, "task_fail": 0})
                row[metric] = count
                totals[metric] += count
            elif metric in _SHAPING_METRICS:
                row = by_task.setdefault(task, {"queued": 0, "running": 0, "task_ok": 0, "task_fail": 0})
                row[metric] = count
                shaping_totals[metric] += count
            elif metric in _CLASSIFY_METRICS:
                row = by_task.setdefault(task, {"queued": 0, "running": 0, "task_ok": 0, "task_fail": 0})
                row[metric] = count
                classify_totals[metric] += count
        state_counts["succeeded"] = int(totals["task_ok"] or 0)
        state_counts["failed"] = int(totals["task_fail"] or 0)
        for stats in (provider_stats, model_stats):
            for row in stats.values():
                requests = int(row.get("requests") or 0)
                total_latency = int(row.get("total_latency_ms") or 0)
                row["avg_latency_ms"] = int(total_latency / requests) if requests > 0 else None
        return {
            "source": "ai",
            "day_key": _day_key or today_key(),
            "updated_at": time.time(),
            "by_task": by_task,
            "totals": totals,
            "state_counts": state_counts,
            "failure_counts": dict(_failure_counts),
            "provider_stats": provider_stats,
            "model_stats": model_stats,
            "shaping": {
                "totals": shaping_totals,
            },
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
        _task_states.clear()
        _failure_counts.clear()
        _provider_stats.clear()
        _model_stats.clear()
    _flush_stop.set()
    _flush_thread = None
