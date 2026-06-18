from app.services.llm_task_metrics import (
    clear_llm_task_metrics_for_tests,
    llm_task_metrics_snapshot,
    merge_llm_task_snapshots,
    record_ai_llm_task,
)


def test_record_ai_llm_task_snapshot() -> None:
    clear_llm_task_metrics_for_tests()
    record_ai_llm_task("repeater_polish", "task_ok")
    record_ai_llm_task("repeater_polish", "task_ok")
    record_ai_llm_task("repeater_fallback", "task_fail")
    snap = llm_task_metrics_snapshot(include_persisted=False)
    assert snap["by_task"]["repeater_polish"]["task_ok"] == 2
    assert snap["by_task"]["repeater_fallback"]["task_fail"] == 1
    assert snap["totals"]["task_ok"] == 2
    assert snap["totals"]["task_fail"] == 1
    clear_llm_task_metrics_for_tests()


def test_merge_llm_task_snapshots() -> None:
    merged = merge_llm_task_snapshots([
        {
            "day_key": "2026-06-17",
            "updated_at": 1.0,
            "by_task": {"llm_chat": {"task_ok": 3, "task_fail": 1}},
            "totals": {"task_ok": 3, "task_fail": 1},
        },
        {
            "day_key": "2026-06-17",
            "updated_at": 2.0,
            "by_task": {"repeater_polish": {"task_ok": 5, "task_fail": 0}},
            "totals": {"task_ok": 5, "task_fail": 0},
        },
    ])
    assert merged["by_task"]["llm_chat"]["task_ok"] == 3
    assert merged["by_task"]["repeater_polish"]["task_ok"] == 5
    assert merged["totals"]["task_ok"] == 8
