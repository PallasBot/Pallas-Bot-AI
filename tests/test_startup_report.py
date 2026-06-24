from __future__ import annotations

from app.core.startup_report import (
    emit_startup_summary,
    register_startup_fact,
    register_startup_warning,
    reset_startup_report_for_tests,
    startup_report_snapshot,
)


def test_emit_startup_summary_once() -> None:
    reset_startup_report_for_tests()
    register_startup_fact("llm", "on")
    register_startup_warning("redis", "unreachable")

    emit_startup_summary(api_version="4.0.0", role="api")
    emit_startup_summary(api_version="4.0.0", role="api")

    snap = startup_report_snapshot()
    assert snap["emitted"] is True
    assert snap["facts"] == {"llm": "on"}
    assert snap["warnings"] == {"redis": "unreachable"}
