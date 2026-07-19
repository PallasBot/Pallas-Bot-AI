"""从 provider 响应中提取 token usage。"""

from __future__ import annotations

from typing import Any


def usage_from_local_chat_response(data: dict[str, Any]) -> tuple[int, int]:
    prompt = int(data.get("prompt_eval_count") or 0)
    completion = int(data.get("eval_count") or 0)
    return max(0, prompt), max(0, completion)


def usage_from_remote_chat_response(data: dict[str, Any]) -> tuple[int, int]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    return max(0, prompt), max(0, completion)
