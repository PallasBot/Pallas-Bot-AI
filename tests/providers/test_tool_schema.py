from __future__ import annotations

import asyncio

import app.providers.tool_loop as tool_loop
from app.providers.tool_loop import complete_with_tool_loop
from app.providers.tool_schema import (
    openai_api_tool_name,
    resolve_canonical_tool_name,
    sanitize_tool_schemas_for_api,
)


def test_openai_api_tool_name_replaces_dots() -> None:
    assert openai_api_tool_name("arknights.operator.get") == "arknights_operator_get"
    assert openai_api_tool_name("llm_chat_clear") == "llm_chat_clear"


def test_sanitize_tool_schemas_for_api() -> None:
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "arknights.skill.get",
                "description": "技能",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    out = sanitize_tool_schemas_for_api(schemas)
    assert out[0]["function"]["name"] == "arknights_skill_get"


def test_resolve_canonical_tool_name_from_api_alias() -> None:
    canonical = {"arknights.operator.get", "llm_chat_clear"}
    assert resolve_canonical_tool_name("arknights_operator_get", canonical) == "arknights.operator.get"


def test_complete_with_tool_loop_accepts_api_alias_name(monkeypatch) -> None:
    calls: list[str] = []

    async def fake_complete_once(messages, *, model, options, tools):
        _ = (model, options, tools)
        if not any(item.get("role") == "tool" for item in messages):
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "arknights_operator_get", "arguments": '{"name":"银灰"}'},
                    }
                ],
            }
        return {"role": "assistant", "content": "银灰是近卫干员。"}

    async def fake_execute_bot_tool(*, name, arguments, metadata):
        calls.append(name)
        _ = (arguments, metadata)
        return {"ok": True, "result": {"found": True}}

    monkeypatch.setattr(tool_loop, "execute_bot_tool", fake_execute_bot_tool)

    schemas = [
        {
            "type": "function",
            "function": {"name": "arknights.operator.get", "description": "x", "parameters": {}},
        }
    ]
    reply, _ = asyncio.run(
        complete_with_tool_loop(
            complete_once=fake_complete_once,
            messages=[{"role": "user", "content": "银灰"}],
            tool_schemas=schemas,
            metadata={},
            model="test",
            options={},
        )
    )
    assert calls == ["arknights.operator.get"]
    assert reply
