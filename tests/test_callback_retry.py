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

    captured: dict = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data=None, files=None, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            captured["files"] = files
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


def test_send_callback_default_timeout_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(callback_mod.settings, "callback_timeout", 10)
    monkeypatch.setattr(callback_mod.settings, "callback_file_timeout", 180)

    captured: dict = {}

    class FakeClient:
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
