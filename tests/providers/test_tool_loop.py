from __future__ import annotations

import asyncio

from app.providers.tool_loop import complete_with_tool_loop, parse_tool_arguments


def test_complete_with_tool_loop_executes_tool() -> None:
    calls: list[str] = []

    async def fake_complete_once(messages, *, model, options, tools):
        _ = (model, options)
        if tools and len(messages) == 1:
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

    import app.providers.tool_loop as tool_loop

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

    import app.providers.tool_loop as tool_loop

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
