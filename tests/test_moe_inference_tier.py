from app.providers.categorizer import request_tier_for_metadata
from app.providers.moe import categorize_request_tier, resolve_inference_tier


def test_categorize_request_tier_short_boundary() -> None:
    assert categorize_request_tier("嗯") == "simple"
    assert categorize_request_tier("早安") == "simple"
    assert categorize_request_tier("早安呀") == "medium"


def test_resolve_inference_tier_allows_llm_chat_simple() -> None:
    assert resolve_inference_tier(task="llm_chat", tier="simple", needs_tools=False) == "simple"


def test_resolve_inference_tier_bumps_simple_when_tools_needed() -> None:
    assert resolve_inference_tier(task="llm_chat", tier="simple", needs_tools=True) == "medium"


def test_resolve_inference_tier_keeps_repeater_polish_lite_simple() -> None:
    assert resolve_inference_tier(task="repeater_polish_lite", tier="simple", needs_tools=False) == "simple"


def test_request_tier_for_metadata_allows_simple_for_short_chat() -> None:
    meta = {
        "task": "llm_chat",
        "classification": {"tier": "simple", "needs_tools": False, "source": "model"},
    }
    assert request_tier_for_metadata("嗯", meta) == "simple"
