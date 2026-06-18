from app.core.config import Settings
from app.providers.router import moe_tier_routing_enabled, resolve_model_name


def test_moe_tier_routing_enabled_when_models_configured() -> None:
    cfg = Settings(
        llm_moe_model_simple="tiny",
        llm_moe_model_medium="medium",
        llm_moe_model_complex="",
    )
    assert moe_tier_routing_enabled(cfg) is True


def test_resolve_model_name_uses_classification_tier() -> None:
    cfg = Settings(
        llm_moe_model_simple="simple-model",
        llm_moe_model_medium="medium-model",
        llm_moe_model_complex="complex-model",
    )
    model = resolve_model_name(
        provider="local",
        metadata={
            "task": "llm_chat",
            "classification": {"tier": "simple", "needs_tools": False, "source": "model"},
        },
        user_text="你好",
        request_model=None,
        cfg=cfg,
    )
    assert model == "simple-model"


def test_resolve_model_name_keeps_simple_for_repeater_select() -> None:
    cfg = Settings(
        llm_moe_model_simple="simple-model",
        llm_moe_model_medium="medium-model",
        llm_moe_model_complex="complex-model",
    )
    model = resolve_model_name(
        provider="local",
        metadata={
            "task": "repeater_select",
            "classification": {"tier": "simple", "needs_tools": False, "source": "heuristic"},
        },
        user_text="【用户消息】今天好烦",
        request_model=None,
        cfg=cfg,
    )
    assert model == "simple-model"


def test_resolve_model_name_keeps_simple_for_repeater_polish() -> None:
    cfg = Settings(
        llm_moe_model_simple="simple-model",
        llm_moe_model_medium="medium-model",
        llm_moe_model_complex="complex-model",
    )
    model = resolve_model_name(
        provider="local",
        metadata={
            "task": "repeater_polish",
            "classification": {"tier": "simple", "needs_tools": False, "source": "heuristic"},
        },
        user_text="原句",
        request_model=None,
        cfg=cfg,
    )
    assert model == "simple-model"


def test_resolve_model_name_bumps_tier_when_tools_needed() -> None:
    cfg = Settings(
        llm_moe_model_simple="simple-model",
        llm_moe_model_medium="medium-model",
        llm_moe_model_complex="complex-model",
    )
    model = resolve_model_name(
        provider="local",
        metadata={"classification": {"tier": "simple", "needs_tools": True, "source": "model"}},
        user_text="查一下银灰",
        request_model=None,
        cfg=cfg,
    )
    assert model == "medium-model"


def test_resolve_model_name_uses_vision_model_when_configured() -> None:
    cfg = Settings(
        llm_moe_model_simple="simple-model",
        llm_moe_model_medium="medium-model",
        llm_moe_model_vision="vision-model",
    )
    model = resolve_model_name(
        provider="local",
        metadata={"task": "llm_chat", "has_image": True},
        user_text="[CQ:image,file=abc]",
        request_model=None,
        cfg=cfg,
    )
    assert model == "vision-model"
