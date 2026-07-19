from __future__ import annotations

from typing import Literal

MoeTier = Literal["simple", "medium", "complex"]


def minimum_tier_for_tools(tier: MoeTier, needs_tools: bool) -> MoeTier:
    if needs_tools and tier == "simple":
        return "medium"
    return tier


def resolve_inference_tier(
    *,
    task: str,
    tier: MoeTier,
    needs_tools: bool = False,
) -> MoeTier:
    _ = task
    return minimum_tier_for_tools(tier, needs_tools)


def categorize_request_tier(user_text: str, metadata: dict | None = None) -> MoeTier:
    text = (user_text or "").strip()
    meta = metadata if isinstance(metadata, dict) else {}
    if meta.get("moe_tier") in ("simple", "medium", "complex"):
        return meta["moe_tier"]

    length = len(text)
    question_marks = text.count("?") + text.count("？")
    if length < 3 and question_marks == 0:
        return "simple"
    if length >= 120 or question_marks >= 2:
        return "complex"
    if any(token in text for token in ("分析", "解释", "为什么", "对比", "步骤", "代码")):
        return "complex"
    return "medium"
