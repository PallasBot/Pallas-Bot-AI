from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.providers.categorizer import (
    RequestClassification,
    categorizer_enabled,
    categorizer_model_name,
    classify_request_heuristic,
    needs_tools_for_request,
    needs_vision_for_request,
    parse_categorizer_payload,
    request_tier_for_metadata,
)
from app.providers.tools import resolve_tool_schemas


def test_parse_categorizer_payload() -> None:
    parsed = parse_categorizer_payload('{"needs_tools": true, "tier": "complex", "needs_vision": false}')
    assert parsed == RequestClassification(needs_tools=True, tier="complex", source="model", needs_vision=False)
    assert parse_categorizer_payload("not json") is None


def test_categorizer_model_fallback_to_moe_simple() -> None:
    cfg = Settings(llm_categorizer_model="", llm_moe_model_simple="tiny:1b")
    assert categorizer_model_name(cfg) == "tiny:1b"
    assert categorizer_enabled(Settings(llm_categorizer_enabled=True, llm_moe_model_simple="tiny:1b"))


def test_needs_tools_from_classification_metadata() -> None:
    meta = {"classification": {"needs_tools": False, "tier": "simple", "source": "model"}}
    assert not needs_tools_for_request("银灰技能", task="llm_chat", metadata=meta)


def test_request_tier_from_classification_metadata() -> None:
    meta = {"classification": {"needs_tools": True, "tier": "complex", "source": "model"}}
    assert request_tier_for_metadata("你好", meta) == "complex"


def test_request_tier_bumps_simple_when_tools_needed() -> None:
    meta = {"classification": {"needs_tools": True, "tier": "simple", "source": "model"}}
    assert request_tier_for_metadata("查一下银灰", meta) == "medium"


def test_normalize_classification_bumps_simple_tier_for_tools() -> None:
    from app.providers.categorizer import normalize_classification

    result = normalize_classification(
        RequestClassification(needs_tools=True, tier="simple", source="model", needs_vision=False)
    )
    assert result.tier == "medium"


def test_classify_request_heuristic() -> None:
    result = classify_request_heuristic("今天不错", task="llm_chat", metadata={"tools_enabled": True})
    assert result.needs_tools is False
    assert result.source == "heuristic"


def test_classify_request_heuristic_operator_lookup() -> None:
    result = classify_request_heuristic("你知道谁是银灰吗", task="llm_chat", metadata={})
    assert result.needs_tools is True


def test_needs_vision_from_has_image_metadata() -> None:
    assert needs_vision_for_request("你好", metadata={"has_image": True})
    assert not needs_vision_for_request("你好", metadata={"has_image": False})


def test_classify_request_heuristic_image_cq() -> None:
    result = classify_request_heuristic("[CQ:image,file=abc]", task="llm_chat", metadata={})
    assert result.needs_vision is True


def test_resolve_tool_schemas_uses_classification() -> None:
    schemas = [{"type": "function", "function": {"name": "arknights.operator.get", "parameters": {}}}]
    meta = {
        "tools_enabled": True,
        "tool_schemas": schemas,
        "classification": {"needs_tools": True, "tier": "medium", "source": "model"},
    }
    assert resolve_tool_schemas(task="llm_chat", metadata=meta, user_text="你好") == schemas


def test_classify_request_async_uses_model(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_complete_local_message(*args, **kwargs):
        return {"content": '{"needs_tools": true, "tier": "medium"}'}

    monkeypatch.setattr(
        "app.providers.categorizer.complete_local_message",
        fake_complete_local_message,
    )
    from app.providers.categorizer import classify_request_async

    cfg = Settings(
        llm_categorizer_enabled=True,
        llm_categorizer_model="tiny:1b",
        llm_categorizer_provider="local",
    )

    async def run():
        return await classify_request_async(
            "查一下银灰",
            task="llm_chat",
            metadata={"tools_enabled": True},
            cfg=cfg,
        )

    result = asyncio.run(run())
    assert result.needs_tools is True
    assert result.tier == "medium"
    assert result.source == "model"
