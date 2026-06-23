"""解析与规范化 Bot 下发的 knowledge metadata。"""

from __future__ import annotations

from typing import Any

from app.schemas.knowledge import KNOWLEDGE_CONTRACT_VERSION


def normalize_knowledge_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    meta = metadata if isinstance(metadata, dict) else {}
    version = meta.get("knowledge_contract_version")
    policy = meta.get("knowledge_policy")
    sources = meta.get("knowledge_sources")
    trace = meta.get("retrieval_trace")
    return {
        "knowledge_contract_version": int(version) if version is not None else None,
        "knowledge_policy": dict(policy) if isinstance(policy, dict) else {},
        "knowledge_sources": list(sources) if isinstance(sources, list) else [],
        "retrieval_trace": dict(trace) if isinstance(trace, dict) else {},
        "contract_supported": version == KNOWLEDGE_CONTRACT_VERSION,
    }


def knowledge_trace_for_agent(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized = normalize_knowledge_metadata(metadata)
    if not normalized.get("contract_supported"):
        return None
    trace = normalized.get("retrieval_trace") or {}
    if not trace:
        return None
    return {
        "hit_count": trace.get("hit_count", 0),
        "sources": list(trace.get("sources") or []),
        "chunks": list(trace.get("chunks") or []),
    }
