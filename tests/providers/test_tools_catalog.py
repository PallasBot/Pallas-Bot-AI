from __future__ import annotations

from app.providers.tools import resolve_tool_schemas


def test_resolve_tool_schemas_prefers_tool_catalog() -> None:
    schemas = resolve_tool_schemas(
        task="llm_chat",
        metadata={
            "tools_enabled": True,
            "tool_catalog": {
                "version": "tool_catalog/v1",
                "tools": [
                    {
                        "name": "arknights.operator.get",
                        "description": "查询干员",
                        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}},
                        "source": "builtin",
                    }
                ],
            },
            "tool_schemas": [{"type": "function", "function": {"name": "legacy.tool", "parameters": {}}}],
        },
        user_text="查一下银灰",
    )
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "arknights.operator.get"


def test_resolve_tool_schemas_accepts_mcp_catalog_entry() -> None:
    schemas = resolve_tool_schemas(
        task="llm_chat",
        metadata={
            "tools_enabled": True,
            "classification": {"needs_tools": True, "tier": "medium", "source": "metadata"},
            "tool_catalog": {
                "version": "tool_catalog/v1",
                "tools": [
                    {
                        "name": "mcp.notion.search",
                        "description": "Search Notion",
                        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                        "source": "mcp",
                        "audit": {"mcp_server_id": "notion"},
                    }
                ],
            },
        },
        user_text="搜一下 notion 任务",
    )

    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "mcp.notion.search"
