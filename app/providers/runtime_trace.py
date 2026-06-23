"""Agent runtime 结构化 trace。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ToolCallTrace(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    tool: str
    args_keys: list[str] = Field(default_factory=list)
    ok: bool = True
    error: str = ""
    result_preview: str = ""


class StageTrace(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    stage: str
    status: str
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)


class AgentRuntimeTrace(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    version: str = "agent_trace/v1"
    agent_stage_plan: list[str] = Field(default_factory=list)
    planner_enabled: bool = False
    retrieve_enabled: bool = False
    tool_loop_enabled: bool = False
    tool_schema_count: int = 0
    tool_call_count: int = 0
    final_stage: str | None = None
    request_snapshot_id: str | None = None
    tool_catalog_version: str | None = None
    rounds: list[dict] = Field(default_factory=list)
    stages: list[StageTrace] = Field(default_factory=list)
    prefetched_tool: str | None = None
    retrieval_trace: dict | None = None
    status: str = "success"
