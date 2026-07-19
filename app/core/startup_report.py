"""聚合 AI 服务启动阶段关键事实，并在启动链尾输出一行摘要。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

from app.core.logger import logger


@dataclass
class StartupFactCollector:
    facts: OrderedDict[str, str] = field(default_factory=OrderedDict)
    warnings: OrderedDict[str, str] = field(default_factory=OrderedDict)
    emitted: bool = False

    def set_fact(self, key: str, value: str | None) -> None:
        text = str(value or "").strip()
        if text:
            self.facts[key] = text

    def set_warning(self, key: str, value: str | None) -> None:
        text = str(value or "").strip()
        if text:
            self.warnings[key] = text


_collector = StartupFactCollector()


def register_startup_fact(key: str, value: str | None) -> None:
    _collector.set_fact(key, value)


def register_startup_warning(key: str, value: str | None) -> None:
    _collector.set_warning(key, value)


def reset_startup_report_for_tests() -> None:
    _collector.facts.clear()
    _collector.warnings.clear()
    _collector.emitted = False


def startup_report_snapshot() -> dict[str, object]:
    return {
        "facts": dict(_collector.facts),
        "warnings": dict(_collector.warnings),
        "emitted": _collector.emitted,
    }


def emit_startup_summary(*, api_version: str, role: str = "api") -> None:
    if _collector.emitted:
        return
    _collector.emitted = True

    parts = [f"v={api_version}", f"role={role}"]
    parts.extend(f"{key}={value}" for key, value in _collector.facts.items())
    logger.info("启动摘要：{}", " | ".join(parts))

    if _collector.warnings:
        warning_text = " | ".join(f"{key}={value}" for key, value in _collector.warnings.items())
        logger.warning("启动降级：{}", warning_text)
