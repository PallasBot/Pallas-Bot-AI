"""方舟干员查人话术：从用户句中提取干员名。"""

from __future__ import annotations

import re

_OPERATOR_GET_TOOL = "arknights.operator.get"

_CQ_CODE_RE = re.compile(r"\[CQ:[^\]]+\]", re.IGNORECASE)

_LOOKUP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"你知道谁是(.+?)[吗嘛]?[？?]?$"),
    re.compile(r"谁是(.+?)[吗嘛]?[？?]?$"),
    re.compile(r"(.+?)是谁[？?]?$"),
    re.compile(r"介绍一下(.+?)[吗嘛]?[？?]?$"),
    re.compile(r"介绍下(.+?)[吗嘛]?[？?]?$"),
    re.compile(r"说说(.+?)[吗嘛]?[？?]?$"),
)


def strip_cq_codes(text: str) -> str:
    return _CQ_CODE_RE.sub("", text or "").strip()


_LOOKUP_PRONOUN_BLOCKLIST = frozenset({"你", "我", "俺", "咱", "本人", "自己"})

_SELF_IDENTITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^你是?谁[吗嘛呀呐]?$"),
    re.compile(r"^我(?:又)?是谁[吗嘛呀呐]?$"),
    re.compile(r"^你知道你是?谁[吗嘛呀呐]?$"),
    re.compile(r"^你知道我(?:又)?是谁[吗嘛呀呐]?$"),
)

_MENTION_RE = re.compile(r"@\S+")


def normalize_lookup_user_text(user_text: str) -> str:
    text = strip_cq_codes(user_text)
    text = _MENTION_RE.sub("", text)
    return re.sub(r"\s+", "", text).strip("，,。！？!? ")


def is_self_identity_question(user_text: str) -> bool:
    text = normalize_lookup_user_text(user_text)
    if not text:
        return False
    return any(pattern.fullmatch(text) for pattern in _SELF_IDENTITY_PATTERNS)


def extract_operator_lookup_name(user_text: str) -> str:
    if is_self_identity_question(user_text):
        return ""
    text = strip_cq_codes(user_text)
    if not text:
        return ""
    for pattern in _LOOKUP_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        name = match.group(1).strip()
        if name in _LOOKUP_PRONOUN_BLOCKLIST:
            return ""
        if 1 <= len(name) <= 20:
            return name
    return ""


def operator_get_tool_registered(registered_names: frozenset[str] | set[str]) -> bool:
    return _OPERATOR_GET_TOOL in registered_names
