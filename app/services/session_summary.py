"""超长会话摘要：用 medium 模型压缩旧轮次。"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logger import logger
from app.providers.local_backend import complete_local
from app.services.llm_messages import normalize_chat_history

_SUMMARY_SYSTEM = (
    "你是会话摘要器。用第三人称简要总结以下多轮对话要点，保留人称、梗与约定。"
    "只输出摘要正文，不超过200字。"
)


def session_summary_settings(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    meta = metadata if isinstance(metadata, dict) else {}
    raw = meta.get("session_summary")
    if isinstance(raw, dict):
        enabled = raw.get("enabled")
        if isinstance(enabled, bool):
            return raw
        if str(enabled or "").strip().lower() in ("1", "true", "yes", "on"):
            return raw
    if settings.llm_session_summary_enabled:
        return {
            "enabled": True,
            "threshold": settings.llm_session_summary_threshold,
            "keep_messages": settings.llm_session_summary_keep_messages,
        }
    return None


def format_transcript(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for item in messages:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        label = "用户" if role == "user" else "助手"
        lines.append(f"{label}：{content}")
    return "\n".join(lines)


async def summarize_chat_history(messages: list[dict[str, str]]) -> str:
    transcript = format_transcript(messages)
    if not transcript.strip():
        return ""
    model = (settings.llm_moe_model_medium or settings.llm_model or "").strip()
    if not model:
        return ""
    try:
        reply = await complete_local(
            [
                {"role": "system", "content": _SUMMARY_SYSTEM},
                {"role": "user", "content": transcript[:4000]},
            ],
            model=model,
            options={"num_predict": 256, "temperature": 0.3},
        )
    except Exception as exc:
        logger.warning("会话摘要失败 err={}", exc)
        return ""
    return str(reply or "").strip()


async def maybe_compact_request_messages(
    request_messages: list[dict[str, Any]] | None,
    *,
    metadata: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    cfg = session_summary_settings(metadata)
    if not cfg or not cfg.get("enabled"):
        return request_messages, None
    history = normalize_chat_history(request_messages or [])
    threshold = max(4, int(cfg.get("threshold") or settings.llm_session_summary_threshold))
    keep = max(2, int(cfg.get("keep_messages") or settings.llm_session_summary_keep_messages))
    if len(history) < threshold:
        return request_messages, None
    old = history[:-keep] if keep < len(history) else []
    recent = history[-keep:] if keep > 0 else []
    if not old:
        return request_messages, None
    summary = await summarize_chat_history(old)
    if not summary:
        return request_messages, None
    summary_message = {"role": "user", "content": f"【此前对话摘要】\n{summary}"}
    compacted = [summary_message, *recent]
    logger.info("会话摘要完成：旧轮={} 保留={} 摘要字数={}", len(old), len(recent), len(summary))
    return compacted, {"summary": summary, "keep_messages": keep}
