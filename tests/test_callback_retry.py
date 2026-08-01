from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest

from app.media.services import callback as callback_mod


def test_should_retry_callback_skips_read_timeout() -> None:
    assert callback_mod.should_retry_callback(httpx.ReadTimeout("timed out")) is False


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


def test_send_callback_uses_file_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
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
    result = asyncio.run(inner("http://localhost/callback/x", {"status": "success"}, files={"file": b"audio"}))

    assert result == {"message": "ok"}
    assert captured["timeout"] == 180
    assert captured["files"] == {"file": b"audio"}
