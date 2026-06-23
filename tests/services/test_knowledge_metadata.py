from __future__ import annotations

from app.providers.tool_loop import build_agent_trace, resolve_agent_stage_plan
from app.services.knowledge_metadata import knowledge_trace_for_agent, normalize_knowledge_metadata


def test_normalize_knowledge_metadata_contract_v1() -> None:
    meta = {
        "knowledge_contract_version": 1,
        "knowledge_policy": {"enabled": True},
        "knowledge_sources": [{"source_id": "pallas.bot_faq"}],
        "retrieval_trace": {"hit_count": 1, "sources": ["pallas.bot_faq"], "chunks": []},
    }
    normalized = normalize_knowledge_metadata(meta)
    assert normalized["contract_supported"] is True
    assert normalized["retrieval_trace"]["hit_count"] == 1


def test_knowledge_trace_for_agent_returns_none_when_unsupported() -> None:
    assert knowledge_trace_for_agent({"knowledge_contract_version": 99}) is None


def test_resolve_agent_stage_plan_accepts_retrieve() -> None:
    assert resolve_agent_stage_plan({"agent_stage_plan": ["retrieve", "generate"]}) == (
        "retrieve",
        "generate",
    )


def test_build_agent_trace_includes_retrieval_trace() -> None:
    trace = build_agent_trace(
        metadata={
            "agent_stage_plan": ["retrieve", "tool_loop", "generate"],
            "knowledge_contract_version": 1,
            "retrieval_trace": {"hit_count": 2, "sources": ["pallas.bot_faq"], "chunks": []},
        },
        tool_schemas=[],
    )
    assert trace["retrieve_enabled"] is True
    assert trace["retrieval_trace"]["hit_count"] == 2
