from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

_LEADING_FILLERS = (
    "其实",
    "这倒是",
    "怎么说呢",
    "确实",
    "一般来说",
    "我觉得",
    "感觉",
)
_SERVICEY_PHRASES = (
    "总的来说",
    "简而言之",
    "如果你愿意的话",
    "如果你需要的话",
    "希望这能帮到你",
)


@dataclass(slots=True)
class LlmRewriteResult:
    reply: str
    applied_rules: tuple[str, ...] = ()


def _task_name(metadata: dict[str, Any] | None) -> str:
    return str((metadata or {}).get("task") or "").strip().lower()


def _cleanup_spacing(text: str) -> str:
    out = re.sub(r"\s+", " ", str(text or "")).strip()
    return out.replace("  ", " ")


def _trim_servicey_phrases(text: str) -> str:
    out = str(text or "")
    changed = False
    for phrase in _SERVICEY_PHRASES:
        next_out = out.replace(phrase, "")
        if next_out != out:
            changed = True
        out = next_out
    return _cleanup_spacing(out).strip("，, "), changed


def _avoid_repeated_leading_filler(text: str, metadata: dict[str, Any] | None) -> str:
    out = str(text or "").strip()
    hint = str((metadata or {}).get("variation_hint") or "")
    if not hint:
        return out, False
    for filler in _LEADING_FILLERS:
        if filler in hint and out.startswith(filler):
            out = out[len(filler) :].lstrip("，, ")
            return out, True
    return out, False


def _trim_overexplaining_reply(text: str, metadata: dict[str, Any] | None) -> str:
    out = str(text or "").strip()
    hint = str((metadata or {}).get("variation_hint") or "")
    if "优先短一点" not in hint or len(out) < 24:
        return out, False
    parts = [chunk.strip() for chunk in re.split(r"(?<=[。！？!?])", out) if chunk.strip()]
    if len(parts) <= 1:
        return out, False
    first = parts[0]
    if len(first) >= 8:
        return first, first != out
    shortened = (first + parts[1]).strip()
    if len(shortened) < len(out):
        return shortened, True
    return out, False


def _adapt_reply_length_for_llm_chat(text: str, metadata: dict[str, Any] | None) -> str:
    out = str(text or "").strip()
    hint = str((metadata or {}).get("variation_hint") or "")
    if _task_name(metadata) != "llm_chat":
        return out, False
    if "优先短一点" not in hint or len(out) < 18:
        return out, False

    parts = [chunk.strip() for chunk in re.split(r"(?<=[。！？!?])", out) if chunk.strip()]
    if not parts:
        return out, False
    if len(parts) == 1:
        single = parts[0]
        if len(single) <= 18:
            return out, False
        commas = [chunk for chunk in re.split(r"(?<=[，、；;])", single) if chunk]
        if len(commas) >= 2:
            clipped = commas[0].strip("，、；; ")
            if clipped and len(clipped) + 2 < len(single):
                if clipped[-1] not in "。！？!?":
                    clipped += "。"
                return clipped, True
        return out, False

    first = parts[0]
    if len(first) <= 12:
        return out, False
    if "，" in first:
        lead = first.split("，", 1)[0].strip()
        if len(lead) >= 6:
            shortened = lead
            if shortened[-1] not in "。！？!?":
                shortened += "。"
            return shortened, True
    if len(first) >= 18:
        clipped = first[:18].rstrip("，、；; ")
        if clipped and clipped[-1] not in "。！？!?":
            clipped += "。"
        return clipped, True
    return out, False


def _soften_template_ending(text: str, metadata: dict[str, Any] | None) -> str:
    out = str(text or "").strip()
    hint = str((metadata or {}).get("variation_hint") or "")
    if "自然收口" not in hint:
        return out, False
    replacements = {
        "差不多就是这样。": "差不多。",
        "大概就是这样。": "大概就这样。",
        "总之就这样。": "就这样。",
    }
    for old, new in replacements.items():
        if out.endswith(old):
            return out[: -len(old)] + new, True
    replaced = re.sub(r"(吧|啦|呀|呢){2,}([。！!？?])?$", r"\2", out)
    return replaced, replaced != out


async def rewrite_llm_reply(
    reply: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> LlmRewriteResult:
    """轻量后处理：去一点客服味和固定开头，不额外发模型请求。"""
    out = _cleanup_spacing(reply)
    applied_rules: list[str] = []
    out, changed = _trim_servicey_phrases(out)
    if changed:
        applied_rules.append("trim_servicey_phrase")
    out, changed = _avoid_repeated_leading_filler(out, metadata)
    if changed:
        applied_rules.append("avoid_repeated_opener")
    out, changed = _trim_overexplaining_reply(out, metadata)
    if changed:
        applied_rules.append("trim_overexplaining")
    out, changed = _adapt_reply_length_for_llm_chat(out, metadata)
    if changed:
        applied_rules.append("adapt_llm_chat_length")
    out, changed = _soften_template_ending(out, metadata)
    if changed:
        applied_rules.append("soften_template_ending")
    return LlmRewriteResult(reply=out or str(reply or ""), applied_rules=tuple(applied_rules))


async def maybe_rewrite_llm_reply(
    reply: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> str:
    result = await rewrite_llm_reply(reply, metadata=metadata)
    return result.reply
