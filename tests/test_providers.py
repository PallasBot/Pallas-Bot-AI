from __future__ import annotations

import pytest

from app.core.config import Settings
from app.providers.chain import route_name_for_provider
from app.providers.moe import categorize_request_tier
from app.providers.router import (
    chain_local_tasks,
    chain_remote_tasks,
    infer_task,
    llm_health_snapshot,
    normalize_provider_mode,
    parse_chain_order,
    parse_task_set,
    remote_is_configured,
    resolve_model_name,
    resolve_provider_order,
)


def test_normalize_provider_mode() -> None:
    assert normalize_provider_mode("remote_only") == "remote_only"
    assert normalize_provider_mode("chain") == "chain"
    assert normalize_provider_mode(None) == "local_only"


def test_route_name_for_provider_distinguishes_agent_tool_loop() -> None:
    assert route_name_for_provider("local", used_tools=True) == "tool_loop"
    assert route_name_for_provider("local", used_tools=True, agent_stage_plan=("plan", "tool_loop", "generate")) == (
        "agent_tool_loop"
    )


def test_parse_chain_order_deduplicates() -> None:
    assert parse_chain_order("local,remote,local") == ["local", "remote"]


def test_infer_task_from_mode() -> None:
    assert infer_task({"mode": "drunk"}) == "drunk"
    assert infer_task({"task": "repeater_polish"}) == "repeater_polish"


def test_categorize_request_tier() -> None:
    assert categorize_request_tier("好") == "simple"
    assert categorize_request_tier("你好") == "simple"
    assert categorize_request_tier("你好啊") == "medium"
    assert categorize_request_tier("请详细分析并对比这两种架构方案的优缺点，给出步骤。") == "complex"


def test_resolve_provider_order_remote_only() -> None:
    cfg = Settings(llm_provider_mode="remote_only")
    assert resolve_provider_order(cfg) == ["remote"]


def test_resolve_provider_order_chain_without_remote_falls_back_local() -> None:
    cfg = Settings(llm_provider_mode="chain", llm_remote_base_url="", llm_remote_api_key="")
    assert resolve_provider_order(cfg) == ["local"]


def test_parse_task_set() -> None:
    default = frozenset({"llm_chat"})
    assert parse_task_set("", default) == default
    assert parse_task_set("repeater_polish, llm_chat", default) == frozenset({"repeater_polish", "llm_chat"})


def test_chain_task_sets_from_settings() -> None:
    cfg = Settings(
        llm_chain_local_tasks="repeater_fallback,repeater_polish",
        llm_chain_remote_tasks="llm_chat",
    )
    assert chain_local_tasks(cfg) == frozenset({"repeater_fallback", "repeater_polish"})
    assert chain_remote_tasks(cfg) == frozenset({"llm_chat"})


def test_resolve_provider_order_flipped_tasks_via_env() -> None:
    cfg = Settings(
        llm_provider_mode="chain",
        llm_remote_base_url="https://api.deepseek.com",
        llm_remote_api_key="secret",
        llm_remote_model="deepseek-v4-flash",
        llm_providers_file="tests/fixtures/missing-providers.toml",
        llm_chain_local_tasks="repeater_fallback,repeater_polish",
        llm_chain_remote_tasks="llm_chat,drunk",
    )
    assert resolve_provider_order(cfg, {"task": "repeater_polish"}) == ["local"]
    assert resolve_provider_order(cfg, {"task": "llm_chat"}) == ["remote"]


def test_resolve_provider_order_repeater_prefers_remote_in_chain() -> None:
    cfg = Settings(
        llm_provider_mode="chain",
        llm_remote_base_url="https://api.deepseek.com",
        llm_remote_api_key="secret",
        llm_remote_model="deepseek-v4-flash",
        llm_providers_file="tests/fixtures/missing-providers.toml",
        llm_chain_local_tasks="llm_chat,drunk",
        llm_chain_remote_tasks="repeater_fallback,repeater_polish",
    )
    assert resolve_provider_order(cfg, {"task": "repeater_fallback"}) == ["remote"]
    assert resolve_provider_order(cfg, {"task": "repeater_polish"}) == ["remote"]


def test_resolve_provider_order_chat_stays_local_in_chain() -> None:
    cfg = Settings(
        llm_provider_mode="chain",
        llm_remote_base_url="https://api.deepseek.com",
        llm_remote_api_key="secret",
        llm_remote_model="deepseek-v4-flash",
        llm_providers_file="tests/fixtures/missing-providers.toml",
        llm_chain_local_tasks="llm_chat,drunk",
        llm_chain_remote_tasks="repeater_fallback,repeater_polish",
    )
    assert resolve_provider_order(cfg, {"task": "llm_chat"}) == ["local"]
    assert resolve_provider_order(cfg, {"mode": "drunk"}) == ["local"]


def test_resolve_provider_order_tier_complex_routes_remote() -> None:
    cfg = Settings(
        llm_provider_mode="local_only",
        llm_remote_base_url="https://api.deepseek.com",
        llm_remote_api_key="secret",
        llm_remote_model="deepseek-v4-flash",
        llm_providers_file="tests/fixtures/missing-providers.toml",
        llm_moe_tier_remote_tiers="complex",
        llm_moe_tier_remote_tasks="llm_chat",
        llm_moe_tier_remote_fallback="local",
    )
    meta = {
        "task": "llm_chat",
        "classification": {"tier": "complex", "needs_tools": False, "source": "model"},
    }
    long_text = "请详细分析并对比这两种架构方案的优缺点，给出步骤。" * 3
    assert resolve_provider_order(cfg, meta, user_text=long_text) == ["remote", "local"]


def test_resolve_provider_order_tier_simple_stays_local_when_only_complex_remote() -> None:
    cfg = Settings(
        llm_provider_mode="local_only",
        llm_remote_base_url="https://api.deepseek.com",
        llm_remote_api_key="secret",
        llm_remote_model="deepseek-v4-flash",
        llm_providers_file="tests/fixtures/missing-providers.toml",
        llm_moe_tier_remote_tiers="complex",
    )
    meta = {
        "task": "llm_chat",
        "classification": {"tier": "simple", "needs_tools": False, "source": "model"},
    }
    assert resolve_provider_order(cfg, meta, user_text="你好") == ["local"]


def test_resolve_provider_order_tier_remote_without_fallback() -> None:
    cfg = Settings(
        llm_provider_mode="chain",
        llm_remote_base_url="https://api.deepseek.com",
        llm_remote_api_key="secret",
        llm_remote_model="deepseek-v4-flash",
        llm_providers_file="tests/fixtures/missing-providers.toml",
        llm_moe_tier_remote_tiers="complex",
        llm_moe_tier_remote_fallback="none",
    )
    meta = {
        "task": "llm_chat",
        "classification": {"tier": "complex", "needs_tools": False, "source": "model"},
    }
    assert resolve_provider_order(cfg, meta, user_text="分析" * 40) == ["remote"]


def test_resolve_model_name_task_override_when_local_multi_model_enabled() -> None:
    cfg = Settings(
        llm_task_model_repeater_polish="tiny-local",
        llm_local_multi_model_enabled=True,
    )
    model = resolve_model_name(
        provider="local",
        metadata={"task": "repeater_polish"},
        user_text="原句",
        request_model=None,
        cfg=cfg,
    )
    assert model == "tiny-local"


def test_resolve_model_name_prefers_runtime_for_primary_local_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.providers.router.get_llm_model", lambda: "runtime-8b")
    cfg = Settings(
        llm_model="default-7b",
        llm_task_model_repeater_polish="tiny-local",
        llm_local_multi_model_enabled=False,
    )
    model = resolve_model_name(
        provider="local",
        metadata={"task": "repeater_polish"},
        user_text="原句",
        request_model=None,
        cfg=cfg,
    )
    assert model == "runtime-8b"


def test_resolve_model_name_task_override_restored_when_local_multi_model_enabled() -> None:
    cfg = Settings(
        llm_task_model_repeater_polish="tiny-local",
        llm_local_multi_model_enabled=True,
    )
    model = resolve_model_name(
        provider="local",
        metadata={"task": "repeater_polish"},
        user_text="原句",
        request_model=None,
        cfg=cfg,
    )
    assert model == "tiny-local"


def test_resolve_model_name_moe_enabled() -> None:
    cfg = Settings(
        llm_moe_enabled=True,
        llm_moe_model_simple="fast-local",
        llm_model="default-local",
        llm_local_multi_model_enabled=True,
    )
    model = resolve_model_name(
        provider="local",
        metadata={"task": "llm_chat"},
        user_text="嗨",
        request_model=None,
        cfg=cfg,
    )
    assert model == "fast-local"


def test_llm_health_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.providers.router.ping_local_provider_sync", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.providers.router.ping_remote_provider_sync", lambda *args, **kwargs: True)
    snap = llm_health_snapshot(
        Settings(
            llm_provider_mode="chain",
            llm_moe_enabled=True,
            llm_providers_file="tests/fixtures/missing-providers.toml",
            llm_chain_local_tasks="llm_chat,drunk",
            llm_chain_remote_tasks="repeater_fallback,repeater_polish",
            llm_moe_model_simple="qwen2.5:0.5b",
        )
    )
    assert snap["provider_mode"] == "chain"
    assert snap["moe_enabled"] is True
    assert snap["active_providers"] == ["local"]
    assert snap["configuration_ok"] is True
    assert "provider_status" in snap
    assert isinstance(snap["provider_status"], list)
    assert snap["health_state"] in {"healthy", "degraded", "unhealthy", "unknown"}
    assert snap["circuit_state"] in {"closed", "open", "half_open"}
    assert snap["provider_status"][0]["health_state"] in {"healthy", "degraded", "unhealthy", "unknown"}
    assert snap["categorizer_enabled"] is True
    assert "local_reachable" in snap


def test_remote_is_configured() -> None:
    cfg_ok = Settings(
        llm_providers_file="tests/fixtures/missing-providers.toml",
        llm_remote_base_url="https://api.example.com/v1",
        llm_remote_api_key="k",
    )
    cfg_bad = Settings(
        llm_providers_file="tests/fixtures/missing-providers.toml",
        llm_remote_base_url="",
        llm_remote_api_key="k",
    )
    assert remote_is_configured(cfg_ok)
    assert not remote_is_configured(cfg_bad)
