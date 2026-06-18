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


def extract_operator_lookup_name(user_text: str) -> str:
    text = strip_cq_codes(user_text)
    if not text:
        return ""
    for pattern in _LOOKUP_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        name = match.group(1).strip()
        if 1 <= len(name) <= 20:
            return name
    return ""


def operator_get_tool_registered(registered_names: frozenset[str] | set[str]) -> bool:
    return _OPERATOR_GET_TOOL in registered_names
