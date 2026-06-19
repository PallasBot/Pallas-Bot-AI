from app.services.llm_task_metrics import (
    clear_llm_task_metrics_for_tests,
    llm_task_metrics_snapshot,
    merge_llm_task_snapshots,
    record_ai_llm_provider_result,
    record_ai_llm_shaping,
    record_ai_llm_task,
    record_ai_llm_task_state,
)


def test_record_ai_llm_task_snapshot() -> None:
    clear_llm_task_metrics_for_tests()
    record_ai_llm_task_state("celery-1", "repeater_polish", "queued")
    record_ai_llm_task_state("celery-2", "repeater_polish", "running")
    record_ai_llm_provider_result(
        task="repeater_polish",
        provider="openai",
        model="gpt-4.1-mini",
        succeeded=True,
        latency_ms=120,
    )
    record_ai_llm_provider_result(
        task="repeater_fallback",
        provider="deepseek",
        model="deepseek-chat",
        succeeded=False,
        latency_ms=480,
        failure_class="provider_error",
    )
    record_ai_llm_task("repeater_polish", "task_ok")
    record_ai_llm_task("repeater_polish", "task_ok")
    record_ai_llm_task("repeater_fallback", "task_fail")
    record_ai_llm_shaping({
        "task": "repeater_polish",
        "variation_applied": True,
        "rewrite_applied_rules": ["avoid_repeated_opener", "trim_overexplaining", "adapt_llm_chat_length"],
    })
    snap = llm_task_metrics_snapshot(include_persisted=False)
    assert snap["by_task"]["repeater_polish"]["queued"] == 1
    assert snap["by_task"]["repeater_polish"]["running"] == 1
    assert snap["by_task"]["repeater_polish"]["task_ok"] == 2
    assert snap["by_task"]["repeater_fallback"]["task_fail"] == 1
    assert snap["totals"]["task_ok"] == 2
    assert snap["totals"]["task_fail"] == 1
    assert snap["by_task"]["repeater_polish"]["variation_applied"] == 1
    assert snap["by_task"]["repeater_polish"]["rewrite_avoid_repeated_opener"] == 1
    assert snap["by_task"]["repeater_polish"]["rewrite_trim_overexplaining"] == 1
    assert snap["by_task"]["repeater_polish"]["rewrite_adapt_llm_chat_length"] == 1
    assert snap["shaping"]["totals"]["variation_applied"] == 1
    assert snap["shaping"]["totals"]["rewrite_avoid_repeated_opener"] == 1
    assert snap["shaping"]["totals"]["rewrite_trim_overexplaining"] == 1
    assert snap["shaping"]["totals"]["rewrite_adapt_llm_chat_length"] == 1
    assert snap["failure_counts"] == {"provider_error": 1}
    assert snap["provider_stats"]["openai"]["succeeded"] == 1
    assert snap["provider_stats"]["deepseek"]["failed"] == 1
    assert snap["provider_stats"]["deepseek"]["recent_failure_class"] == "provider_error"
    assert snap["provider_stats"]["openai"]["avg_latency_ms"] == 120
    assert snap["model_stats"]["gpt-4.1-mini"]["succeeded"] == 1
    assert snap["model_stats"]["deepseek-chat"]["failed"] == 1
    assert snap["state_counts"] == {
        "queued": 1,
        "running": 1,
        "succeeded": 2,
        "failed": 1,
    }
    clear_llm_task_metrics_for_tests()


def test_merge_llm_task_snapshots() -> None:
    merged = merge_llm_task_snapshots([
        {
            "day_key": "2026-06-17",
            "updated_at": 1.0,
            "by_task": {
                "llm_chat": {
                    "queued": 2,
                    "running": 1,
                    "task_ok": 3,
                    "task_fail": 1,
                    "variation_applied": 2,
                    "rewrite_trim_servicey_phrase": 1,
                }
            },
            "totals": {"task_ok": 3, "task_fail": 1},
            "shaping": {"totals": {"variation_applied": 2, "rewrite_trim_servicey_phrase": 1}},
            "failure_counts": {"provider_error": 2},
            "provider_stats": {
                "openai": {
                    "requests": 2,
                    "succeeded": 1,
                    "failed": 1,
                    "total_latency_ms": 600,
                    "recent_failure_class": "provider_error",
                }
            },
            "model_stats": {
                "gpt-4.1-mini": {
                    "requests": 2,
                    "succeeded": 1,
                    "failed": 1,
                    "total_latency_ms": 600,
                    "recent_failure_class": "provider_error",
                }
            },
        },
        {
            "day_key": "2026-06-17",
            "updated_at": 2.0,
            "by_task": {
                "repeater_polish": {
                    "queued": 1,
                    "running": 0,
                    "task_ok": 5,
                    "task_fail": 0,
                    "variation_applied": 1,
                    "rewrite_trim_overexplaining": 1,
                    "rewrite_adapt_llm_chat_length": 1,
                }
            },
            "totals": {"task_ok": 5, "task_fail": 0},
            "shaping": {
                "totals": {
                    "variation_applied": 1,
                    "rewrite_trim_overexplaining": 1,
                    "rewrite_adapt_llm_chat_length": 1,
                }
            },
            "failure_counts": {"internal_error": 1},
            "provider_stats": {
                "deepseek": {
                    "requests": 1,
                    "succeeded": 1,
                    "failed": 0,
                    "total_latency_ms": 180,
                    "recent_failure_class": None,
                }
            },
            "model_stats": {
                "deepseek-chat": {
                    "requests": 1,
                    "succeeded": 1,
                    "failed": 0,
                    "total_latency_ms": 180,
                    "recent_failure_class": None,
                }
            },
        },
    ])
    assert merged["by_task"]["llm_chat"]["queued"] == 2
    assert merged["by_task"]["llm_chat"]["running"] == 1
    assert merged["by_task"]["llm_chat"]["task_ok"] == 3
    assert merged["by_task"]["repeater_polish"]["task_ok"] == 5
    assert merged["by_task"]["llm_chat"]["variation_applied"] == 2
    assert merged["by_task"]["repeater_polish"]["variation_applied"] == 1
    assert merged["by_task"]["llm_chat"]["rewrite_trim_servicey_phrase"] == 1
    assert merged["by_task"]["repeater_polish"]["rewrite_trim_overexplaining"] == 1
    assert merged["by_task"]["repeater_polish"]["rewrite_adapt_llm_chat_length"] == 1
    assert merged["totals"]["task_ok"] == 8
    assert merged["shaping"]["totals"]["variation_applied"] == 3
    assert merged["shaping"]["totals"]["rewrite_trim_servicey_phrase"] == 1
    assert merged["shaping"]["totals"]["rewrite_trim_overexplaining"] == 1
    assert merged["shaping"]["totals"]["rewrite_adapt_llm_chat_length"] == 1
    assert merged["failure_counts"] == {
        "provider_error": 2,
        "internal_error": 1,
    }
    assert merged["provider_stats"]["openai"]["requests"] == 2
    assert merged["provider_stats"]["openai"]["avg_latency_ms"] == 300
    assert merged["provider_stats"]["deepseek"]["requests"] == 1
    assert merged["model_stats"]["gpt-4.1-mini"]["avg_latency_ms"] == 300
    assert merged["state_counts"] == {
        "queued": 3,
        "running": 1,
        "succeeded": 8,
        "failed": 1,
    }
