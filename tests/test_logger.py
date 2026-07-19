from __future__ import annotations

import logging
from unittest.mock import MagicMock

from app.core.logger import (
    configure_stdlib_logging,
    effective_log_format,
    log_id_clause,
    module_display_name,
    patch_log_record,
    resolve_log_level,
    short_log_id,
    stdlib_level,
    task_log,
)


def test_resolve_log_level_fallback() -> None:
    assert resolve_log_level("info") == "INFO"
    assert resolve_log_level("bogus", fallback="WARNING") == "WARNING"


def test_configure_stdlib_logging_quiet_framework() -> None:
    configure_stdlib_logging()
    assert logging.getLogger("uvicorn.access").level >= logging.WARNING
    assert logging.getLogger("celery.worker.strategy").level >= logging.WARNING
    assert logging.getLogger("aiohttp.access").level >= logging.WARNING
    assert logging.getLogger("PIL").level >= logging.WARNING


def test_configure_stdlib_logging_skips_quiet_when_debug(monkeypatch) -> None:
    monkeypatch.setattr("app.core.logger.settings.log_level", "DEBUG")
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    configure_stdlib_logging()
    assert logging.getLogger("httpx").level == logging.NOTSET


def test_stdlib_level_maps_names() -> None:
    assert stdlib_level("WARNING") == logging.WARNING
    assert stdlib_level("ERROR") == logging.ERROR


def test_short_log_id_truncates(monkeypatch) -> None:
    monkeypatch.setattr("app.core.logger.settings.log_id_chars", 8)
    assert short_log_id("01KV95T5WZNKAMQWA8NZ4ZK8G") == "01KV95T5"
    assert log_id_clause("01KV95T5WZNKAMQWA8NZ4ZK8G") == "单号=01KV95T5 "


def test_short_log_id_omit_when_zero(monkeypatch) -> None:
    monkeypatch.setattr("app.core.logger.settings.log_id_chars", 0)
    assert not short_log_id("01KV95T5WZNKAMQWA8NZ4ZK8G")
    assert not log_id_clause("01KV95T5WZNKAMQWA8NZ4ZK8G")


def test_patch_log_record_short_module() -> None:
    record: dict = {"name": "app.tasks.llm.chat_tasks", "line": 144, "extra": {}}
    patch_log_record(record)
    assert record["extra"]["loc"] == "ai.task:144"


def test_module_display_name_uses_aliases() -> None:
    assert module_display_name("app.providers.tool_loop") == "ai.providers"
    assert module_display_name("uvicorn.error") == "uvicorn"


def test_effective_log_format_uses_short_loc_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr("app.core.logger.settings.log_loc_short", True)
    assert "extra[loc]" in effective_log_format()


def test_task_log_defaults_to_debug_when_verbose_disabled(monkeypatch) -> None:
    fake_logger = MagicMock()
    monkeypatch.setattr("app.core.logger.loguru_logger", fake_logger)
    monkeypatch.setattr("app.core.logger.settings.log_verbose_tasks", False)

    task_log("hello {}", "world")

    fake_logger.log.assert_called_once_with("DEBUG", "hello {}", "world")


def test_task_log_uses_info_when_verbose_enabled(monkeypatch) -> None:
    fake_logger = MagicMock()
    monkeypatch.setattr("app.core.logger.loguru_logger", fake_logger)
    monkeypatch.setattr("app.core.logger.settings.log_verbose_tasks", True)

    task_log("hello {}", "world")

    fake_logger.log.assert_called_once_with("INFO", "hello {}", "world")
