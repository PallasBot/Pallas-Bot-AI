from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest

from app.media.services import callback as callback_mod


def test_should_retry_callback_skips_read_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[str] = []

    def capture_warning(msg: str, *args, **kwargs) -> None:
        warnings.append(msg.format(*args) if args else msg)

    monkeypatch.setattr(callback_mod.logger, "warning", capture_warning)
    assert callback_mod.should_retry_callback(httpx.ReadTimeout("timed out")) is False
    assert warnings
    assert "ReadTimeout" in warnings[0]
    assert "skip retry" in warnings[0]


def test_should_retry_callback_allows_connect_error() -> None:
    assert callback_mod.should_retry_callback(httpx.ConnectError("boom")) is True


def test_should_retry_callback_skips_when_token_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(callback_mod.settings, "api_bearer_token", "")
    assert callback_mod.should_retry_callback(httpx.ConnectError("boom")) is False


def test_should_retry_callback_skips_4xx() -> None:
    request = httpx.Request("POST", "http://localhost/callback/x")
    response = httpx.Response(404, request=request)
    err = httpx.HTTPStatusError("nf", request=request, response=response)
    assert callback_mod.should_retry_callback(err) is False


def test_should_retry_callback_allows_5xx() -> None:
    request = httpx.Request("POST", "http://localhost/callback/x")
    response = httpx.Response(502, request=request)
    err = httpx.HTTPStatusError("bad", request=request, response=response)
    assert callback_mod.should_retry_callback(err) is True


def test_resolve_callback_timeout_respects_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(callback_mod.settings, "callback_timeout", 10)
    monkeypatch.setattr(callback_mod.settings, "callback_file_timeout", 180)
    assert callback_mod.resolve_callback_timeout(use_file_timeout=False) == 10
    assert callback_mod.resolve_callback_timeout(use_file_timeout=True) == 180


def test_send_callback_uses_explicit_file_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(callback_mod.settings, "callback_timeout", 10)
    monkeypatch.setattr(callback_mod.settings, "callback_file_timeout", 180)
    monkeypatch.setattr(callback_mod.settings, "api_bearer_token", "secret-token")

    captured: dict = {}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data=None, files=None, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            captured["files"] = files
            captured["headers"] = kwargs.get("headers")
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={"message": "ok"})
            return resp

    monkeypatch.setattr(callback_mod.httpx, "AsyncClient", FakeClient)

    inner = getattr(callback_mod.send_callback, "__wrapped__", callback_mod.send_callback)
    result = asyncio.run(
        inner(
            "http://localhost/callback/x",
            {"status": "success"},
            files={"file": b"audio"},
            use_file_timeout=True,
        )
    )

    assert result == {"message": "ok"}
    assert captured["timeout"] == 180
    assert captured["files"] == {"file": b"audio"}
    assert captured["headers"] == {"Authorization": "Bearer secret-token"}


def test_send_callback_default_timeout_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(callback_mod.settings, "callback_timeout", 10)
    monkeypatch.setattr(callback_mod.settings, "callback_file_timeout", 180)
    monkeypatch.setattr(callback_mod.settings, "api_bearer_token", "secret-token")

    captured: dict = {}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data=None, files=None, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={"message": "ok"})
            return resp

    monkeypatch.setattr(callback_mod.httpx, "AsyncClient", FakeClient)
    inner = getattr(callback_mod.send_callback, "__wrapped__", callback_mod.send_callback)
    # 即使误传 files，未显式 use_file_timeout=True 时仍用短超时
    asyncio.run(inner("http://localhost/callback/x", {"status": "success"}, files={"file": b"x"}))
    assert captured["timeout"] == 10


@pytest.mark.parametrize("status", ["success", "failed"])
def test_callback_sends_bearer_for_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    monkeypatch.setattr(callback_mod.settings, "api_bearer_token", "secret-token")
    captured: list[dict] = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, _url, data=None, **kwargs):
            captured.append({"data": data, **kwargs})
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json = MagicMock(return_value={"message": "ok"})
            return resp

    monkeypatch.setattr(callback_mod.httpx, "AsyncClient", FakeClient)
    asyncio.run(callback_mod.callback("req-auth", status=status, text="result"))
    assert captured[0]["headers"] == {"Authorization": "Bearer secret-token"}


def test_send_callback_refuses_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(callback_mod.settings, "api_bearer_token", "")
    calls: list[None] = []

    class FakeClient:
        async def __aenter__(self):
            calls.append(None)
            return self

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(callback_mod.httpx, "AsyncClient", FakeClient)
    inner = getattr(callback_mod.send_callback, "__wrapped__", callback_mod.send_callback)
    with pytest.raises(RuntimeError, match="not configured"):
        asyncio.run(inner("http://localhost/callback/x", {"status": "failed"}))
    assert not calls


def test_callback_error_log_does_not_include_exception_message(monkeypatch: pytest.MonkeyPatch) -> None:
    messages: list[str] = []

    async def fail(*_args, **_kwargs):
        raise RuntimeError("secret-token in request headers")

    def capture_error(message: str, *args, **_kwargs) -> None:
        messages.append(message.format(*args) if args else message)

    monkeypatch.setattr(callback_mod, "send_callback", fail)
    monkeypatch.setattr(callback_mod.logger, "error", capture_error)
    asyncio.run(callback_mod.callback("req-auth-log", status="failed"))
    assert messages
    assert "RuntimeError" in messages[0]
    assert "secret-token" not in messages[0]
