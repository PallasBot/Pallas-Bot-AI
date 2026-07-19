from __future__ import annotations

from app.services.llm_messages import (
    build_chat_messages,
    count_history_messages,
    is_pg_session,
    normalize_chat_history,
)
from app.session import del_session, save_messages


def test_is_pg_session_truthy_values() -> None:
    assert is_pg_session({"pg_session": True})
    assert is_pg_session({"pg_session": "true"})
    assert not is_pg_session({"pg_session": False})
    assert not is_pg_session(None)


def test_normalize_chat_history_filters_roles() -> None:
    raw = [
        {"role": "system", "content": "skip"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "嗨"},
        {"role": "tool", "content": "x"},
        {"role": "user", "content": ""},
    ]
    assert normalize_chat_history(raw) == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "嗨"},
    ]


def test_build_chat_messages_pg_uses_bot_history() -> None:
    request_messages = [
        {"role": "user", "content": "第一句"},
        {"role": "assistant", "content": "第二句"},
        {"role": "user", "content": "第三句"},
    ]
    messages, mode = build_chat_messages(
        "system-a",
        {"pg_session": True},
        "sess-ignored",
        "第三句",
        request_messages,
    )
    assert mode == "pg"
    assert messages[0] == {"role": "system", "content": "system-a"}
    assert messages[1:] == request_messages


def test_build_chat_messages_redis_appends_user_turn() -> None:
    session = "redis-session-test"
    del_session(session)
    messages, mode = build_chat_messages("sys", {}, session, "新一句", None)
    assert mode == "redis"
    assert messages[-1] == {"role": "user", "content": "新一句"}
    assert messages[0]["role"] == "system"
    del_session(session)


def test_count_history_messages_pg_vs_redis() -> None:
    session = "redis-count-test"
    del_session(session)
    save_messages(
        session,
        [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ],
    )
    assert count_history_messages({}, session, None, "c") == 3
    pg_count = count_history_messages(
        {"pg_session": True},
        session,
        [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ],
        "c",
    )
    assert pg_count == 3
    del_session(session)
