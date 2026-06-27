from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_LEADING_FILLERS = (
    "哈喽",
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
_LLM_CHAT_SCAFFOLD_PREFIXES = (
    "不过没事",
    "先别急",
    "我感觉",
    "我觉得",
    "大概率",
    "一般来说",
)
_OPENER_LABEL_PREFIX = "最近几轮别再用这些开头："
_ANIMAL_OPENER_RE = re.compile(r"^(哞~|喵~|喵呜~|哞呜~)")
_KAOMOJI_SUFFIX_RE = re.compile(r"\(\*[^)]{1,16}\*\)\s*$")
_KAOMOJI_ANY_RE = re.compile(r"\(\*[^)]{1,16}\*\)")
_TRAILING_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F"
    r"\U0001F600-\U0001F64F\U0000200D"
    r"]+$",
    re.UNICODE,
)
_CQ_AT_LEADING_RE = re.compile(r"^\s*\[CQ:at,qq=(?P<qq>\d+)(?:[^\]]*)?\]", re.IGNORECASE)
_AT_PLAIN_LEADING_RE = re.compile(r"^\s*@(?P<name>[^\s@，,。！!？?：:;；]{1,24})")
_DEFAULT_SELF_ALIASES = ("牛牛", "帕拉斯", "Pallas", "帕拉丝")


@dataclass(slots=True)
class LlmRewriteResult:
    reply: str
    applied_rules: tuple[str, ...] = ()


def _task_name(metadata: dict[str, Any] | None) -> str:
    return str((metadata or {}).get("task") or "").strip().lower()


def _self_alias_names(metadata: dict[str, Any] | None) -> set[str]:
    names = {item.casefold() for item in _DEFAULT_SELF_ALIASES}
    meta = metadata or {}
    raw = meta.get("self_aliases")
    if isinstance(raw, list):
        for item in raw:
            text = str(item or "").strip()
            if text:
                names.add(text.casefold())
    return names


def _strip_leading_self_at_mentions(text: str, metadata: dict[str, Any] | None) -> tuple[str, bool]:
    meta = metadata or {}
    bot_self_id = meta.get("bot_id")
    bot_id_text = str(bot_self_id).strip() if bot_self_id is not None else ""
    names = _self_alias_names(meta)
    out = str(text or "").strip()
    changed = False
    while out:
        step = False
        cq_match = _CQ_AT_LEADING_RE.match(out)
        if cq_match and (not bot_id_text or cq_match.group("qq") == bot_id_text):
            out = out[cq_match.end() :].lstrip()
            step = True
        else:
            at_match = _AT_PLAIN_LEADING_RE.match(out)
            if at_match and at_match.group("name").casefold() in names:
                out = out[at_match.end() :].lstrip()
                step = True
        if not step:
            break
        changed = True
    return out, changed


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


def _extract_repeated_opener_labels(metadata: dict[str, Any] | None) -> list[str]:
    hint = str((metadata or {}).get("variation_hint") or "")
    if not hint or _OPENER_LABEL_PREFIX not in hint:
        return []
    labels: list[str] = []
    for raw_line in hint.splitlines():
        line = raw_line.strip()
        if _OPENER_LABEL_PREFIX not in line:
            continue
        suffix = line.split(_OPENER_LABEL_PREFIX, 1)[1].strip()
        labels.extend(item.strip() for item in suffix.split("、") if item.strip())
    return labels


def _trim_repeated_opener_family(text: str, metadata: dict[str, Any] | None) -> tuple[str, str | None]:
    out = str(text or "").strip()
    hint = str((metadata or {}).get("variation_hint") or "")
    labels = _extract_repeated_opener_labels(metadata)
    matched = _ANIMAL_OPENER_RE.match(out)
    if matched and ("动物口癖" in hint or any(label in {"哞~", "喵~", "喵呜~", "哞呜~"} for label in labels)):
        trimmed = out[matched.end() :].lstrip("，,。！!？?~～ ")
        if trimmed and trimmed != out:
            return trimmed, "trim_repeated_animal_opener"
    if not labels:
        return out, None
    if "哈哈类" in labels:
        matched = re.match(r"^(哈哈+|呵呵+|嘿嘿+)", out)
        if matched:
            trimmed = out[matched.end() :].lstrip("，,。！!？?~～ ")
            if trimmed and trimmed != out:
                return trimmed, "trim_repeated_laugh_opener"
    if "语气词类" in labels:
        matched = re.match(r"^([欸哎唉呃额]{1,3})", out)
        if matched:
            trimmed = out[matched.end() :].lstrip("，,。！!？?~～ ")
            if trimmed and trimmed != out:
                return trimmed, "trim_repeated_sigh_opener"
    for label in labels:
        if label in {"哈哈类", "语气词类"}:
            continue
        if out.startswith(label):
            trimmed = out[len(label) :].lstrip("，,。！!？?~～ ")
            if trimmed and trimmed != out:
                return trimmed, "trim_repeated_generic_opener"
    return out, None


def _trim_kaomoji_suffix(text: str, metadata: dict[str, Any] | None) -> tuple[str, bool]:
    out = str(text or "").strip()
    if _task_name(metadata) == "llm_chat":
        return out, False
    hint = str((metadata or {}).get("variation_hint") or "")
    if "颜文字" not in hint and "(*" not in hint:
        return out, False
    replaced = _KAOMOJI_SUFFIX_RE.sub("", out).rstrip("，,。！!？?~～ ")
    if replaced and replaced != out:
        return replaced, True
    return out, False


def _sanitize_llm_chat_decorations(text: str) -> tuple[str, tuple[str, ...]]:
    out = str(text or "").strip()
    applied: list[str] = []

    without_kaomoji = _KAOMOJI_ANY_RE.sub("", out)
    without_kaomoji = re.sub(r"\s{2,}", " ", without_kaomoji).strip()
    if without_kaomoji and without_kaomoji != out:
        out = without_kaomoji
        applied.append("trim_kaomoji")

    while True:
        next_out = _TRAILING_EMOJI_RE.sub("", out).rstrip()
        if next_out == out:
            break
        out = next_out
        if "trim_trailing_emoji" not in applied:
            applied.append("trim_trailing_emoji")

    return out, tuple(applied)


def _persona_shaping_active(metadata: dict[str, Any] | None) -> bool:
    meta = metadata or {}
    if bool(meta.get("persona_shaping_active")):
        return True
    return bool(str(meta.get("persona_affect_block") or "").strip())


def _trim_overexplaining_reply(text: str, metadata: dict[str, Any] | None) -> str:
    if _persona_shaping_active(metadata):
        return str(text or "").strip(), False
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
    if _persona_shaping_active(metadata):
        return out, False
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


def _trim_llm_chat_scaffold(text: str, metadata: dict[str, Any] | None) -> str:
    out = str(text or "").strip()
    if _persona_shaping_active(metadata):
        return out, False
    if _task_name(metadata) != "llm_chat":
        return out, False
    hint = str((metadata or {}).get("variation_hint") or "")
    if "先判断一下、再补解释" not in hint:
        return out, False

    parts = [chunk.strip() for chunk in re.split(r"(?<=[。！？!?])", out) if chunk.strip()]
    if not parts:
        return out, False

    kept: list[str] = []
    changed = False
    for idx, part in enumerate(parts):
        current = part
        if idx > 0:
            for prefix in _LLM_CHAT_SCAFFOLD_PREFIXES:
                if current.startswith(prefix):
                    current = current[len(prefix) :].lstrip("，, ")
                    changed = True
                    break
        if any(token in current for token in ("大概率还是", "一般来说", "前面节奏没踩稳")):
            changed = True
            continue
        if current:
            kept.append(current)

    if not kept:
        return out, False
    if len(kept) >= 2:
        kept = [kept[0], kept[-1]]
        changed = True
    rebuilt = "".join(kept).strip()
    return rebuilt or out, changed


def _soften_template_ending(text: str, metadata: dict[str, Any] | None) -> tuple[str, bool]:
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
    out, opener_rule = _trim_repeated_opener_family(out, metadata)
    if opener_rule:
        applied_rules.append(opener_rule)
    out, changed = _trim_kaomoji_suffix(out, metadata)
    if changed:
        applied_rules.append("trim_kaomoji_suffix")
    if _task_name(metadata) == "llm_chat":
        out, deco_rules = _sanitize_llm_chat_decorations(out)
        applied_rules.extend(deco_rules)
        out, changed = _strip_leading_self_at_mentions(out, metadata)
        if changed:
            applied_rules.append("strip_self_at_mention")
    out, changed = _trim_overexplaining_reply(out, metadata)
    if changed:
        applied_rules.append("trim_overexplaining")
    out, changed = _adapt_reply_length_for_llm_chat(out, metadata)
    if changed:
        applied_rules.append("adapt_llm_chat_length")
    out, changed = _trim_llm_chat_scaffold(out, metadata)
    if changed:
        applied_rules.append("trim_llm_chat_scaffold")
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
