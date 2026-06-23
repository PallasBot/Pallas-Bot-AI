from __future__ import annotations

import asyncio

import app.providers.tool_loop as tool_loop
from app.providers.tool_loop import (
    complete_with_tool_loop,
    parse_tool_arguments,
    resolve_agent_stage_plan,
    tool_schemas_for_metadata,
)


def test_complete_with_tool_loop_executes_tool() -> None:
    calls: list[str] = []

    async def fake_complete_once(messages, *, model, options, tools):
        _ = (model, options)
        if tools and not any(item.get("role") == "tool" for item in messages):
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "arknights.operator.get", "arguments": '{"name":"银灰"}'},
                    }
                ],
            }
        return {"role": "assistant", "content": "银灰是近卫。"}

    async def fake_execute_bot_tool(*, name, arguments, metadata):
        calls.append(name)
        _ = (arguments, metadata)
        return {"ok": True, "result": {"found": True}}

    tool_loop.execute_bot_tool = fake_execute_bot_tool  # type: ignore[method-assign]

    reply, message = asyncio.run(
        complete_with_tool_loop(
            complete_once=fake_complete_once,
            messages=[{"role": "user", "content": "银灰是谁"}],
            tool_schemas=[{"type": "function", "function": {"name": "arknights.operator.get", "parameters": {}}}],
            metadata={"bot_id": 1, "group_id": 2, "user_id": 3},
            model="test",
            options={},
        )
    )
    assert calls == ["arknights.operator.get"]
    assert "银灰" in reply
    assert message["role"] == "assistant"
    assert message["_agent_trace"]["tool_call_count"] == 1
    assert message["_agent_trace"]["rounds"][0]["tool_calls"] == ["arknights.operator.get"]


def test_complete_with_tool_loop_prefetches_operator_when_model_skips_tool() -> None:
    calls: list[str] = []
    complete_rounds = 0

    async def fake_complete_once(messages, *, model, options, tools):
        nonlocal complete_rounds
        complete_rounds += 1
        _ = (model, options, tools)
        if complete_rounds == 1:
            return {"role": "assistant", "content": "银灰是她，会瞬移。"}
        return {"role": "assistant", "content": "银灰是谢拉格军阀，近卫干员。"}

    async def fake_execute_bot_tool(*, name, arguments, metadata):
        calls.append(name)
        assert arguments == {"name": "银灰"}
        _ = metadata
        return {"ok": True, "result": {"name": "银灰", "profession": "近卫"}}

    tool_loop.execute_bot_tool = fake_execute_bot_tool  # type: ignore[method-assign]

    reply, message = asyncio.run(
        complete_with_tool_loop(
            complete_once=fake_complete_once,
            messages=[{"role": "user", "content": "你知道谁是银灰吗"}],
            tool_schemas=[{"type": "function", "function": {"name": "arknights.operator.get", "parameters": {}}}],
            metadata={"bot_id": 1, "group_id": 2, "user_id": 3, "task": "llm_chat", "tools_enabled": True},
            model="test",
            options={},
            user_text="你知道谁是银灰吗",
        )
    )
    assert calls == ["arknights.operator.get"]
    assert complete_rounds == 2
    assert "近卫" in reply
    assert message["role"] == "assistant"


def test_parse_tool_arguments_json() -> None:
    assert parse_tool_arguments('{"name": "银灰"}') == {"name": "银灰"}


def test_resolve_agent_stage_plan_normalizes_values() -> None:
    assert resolve_agent_stage_plan({"agent_stage_plan": ["Plan", " tool_loop ", "", None]}) == ("plan", "tool_loop")


def test_tool_schemas_for_metadata_respects_agent_stage_plan() -> None:
    schemas = tool_schemas_for_metadata(
        {
            "task": "llm_chat",
            "tools_enabled": True,
            "tool_schemas": [{"type": "function", "function": {"name": "kb_lookup"}}],
            "agent_stage_plan": ["generate"],
        },
        user_text="查一下银灰",
    )
    assert schemas == []


def test_complete_with_tool_loop_inserts_planner_reminder() -> None:
    seen_messages: list[dict[str, str]] = []

    async def fake_complete_once(messages, *, model, options, tools):
        _ = (model, options, tools)
        seen_messages[:] = messages
        return {"role": "assistant", "content": "先查工具再回答。"}

    reply, _message = asyncio.run(
        complete_with_tool_loop(
            complete_once=fake_complete_once,
            messages=[{"role": "user", "content": "银灰是谁"}],
            tool_schemas=[{"type": "function", "function": {"name": "arknights.operator.get", "parameters": {}}}],
            metadata={"agent_stage_plan": ["plan", "tool_loop", "generate"]},
            model="test",
            options={},
            user_text="银灰是谁",
        )
    )
    assert reply == "先查工具再回答。"
    assert any("回答计划" in str(item.get("content") or "") for item in seen_messages if item.get("role") == "system")
    assert _message["_agent_trace"]["planner_enabled"] is True
    assert _message["_agent_trace"]["agent_stage_plan"] == ["plan", "tool_loop", "generate"]
