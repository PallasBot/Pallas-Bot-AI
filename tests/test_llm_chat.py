from __future__ import annotations

from app.core.config import settings
from app.schemas.llm_chat import LlmChatCompletionRequest, LlmChatMessage, LlmChatMode
from app.services.llm_chat import extract_user_text, resolve_chat_options, resolve_chat_temperature


def test_extract_user_text_uses_last_user_message() -> None:
    request = LlmChatCompletionRequest(
        session_id="s1",
        system="sys",
        messages=[
            LlmChatMessage(role="assistant", content="hi"),
            LlmChatMessage(role="user", content="  你好  "),
        ],
    )
    assert extract_user_text(request) == "你好"


def test_resolve_chat_temperature_drunk_mode(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_drunk_temperature", 1.2)
    monkeypatch.setattr(settings, "llm_temperature", 0.55)
    assert resolve_chat_temperature(LlmChatMode.DRUNK) == 1.2
    assert resolve_chat_temperature(LlmChatMode.NORMAL) == 0.55


def test_resolve_chat_options_passes_token_count() -> None:
    request = LlmChatCompletionRequest(
        session_id="s1",
        system="sys",
        messages=[LlmChatMessage(role="user", content="x")],
        metadata={"mode": "drunk", "token_count": 50},
    )
    options = resolve_chat_options(request)
    assert options["num_predict"] == 50
    assert options["temperature"] >= 0.0


def test_resolve_chat_options_prefers_metadata_temperature() -> None:
    request = LlmChatCompletionRequest(
        session_id="s1",
        system="sys",
        messages=[LlmChatMessage(role="user", content="x")],
        metadata={"mode": "normal", "temperature": 0.72},
    )
    options = resolve_chat_options(request)
    assert options["temperature"] == 0.72


def test_resolve_chat_options_passes_think_override() -> None:
    request = LlmChatCompletionRequest(
        session_id="s1",
        system="sys",
        messages=[LlmChatMessage(role="user", content="x")],
        metadata={"think": True},
    )
    assert resolve_chat_options(request)["think"] is True
