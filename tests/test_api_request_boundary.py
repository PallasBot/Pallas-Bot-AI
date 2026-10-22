from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from app.core.config import settings
from app.http.middleware import APIRequestBoundaryMiddleware


def run_request(
    monkeypatch: pytest.MonkeyPatch,
    *,
    headers: list[tuple[bytes, bytes]],
    request_messages: list[dict[str, Any]],
    max_bytes: int = 8,
) -> tuple[list[dict[str, Any]], list[bytes], int, bool]:
    monkeypatch.setattr(settings, "api_bearer_token", "secret-token")
    monkeypatch.setattr(settings, "api_max_request_bytes", max_bytes)
    pending = iter(request_messages)
    received = 0
    sent: list[dict[str, Any]] = []
    forwarded_body: list[bytes] = []
    called = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        received += 1
        return next(pending)

    async def app(scope: dict[str, Any], app_receive: Callable[[], Awaitable[dict[str, Any]]], send) -> None:
        nonlocal called
        called = True
        while True:
            message = await app_receive()
            if message["type"] == "http.disconnect":
                break
            forwarded_body.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    middleware = APIRequestBoundaryMiddleware(app)
    asyncio.run(
        middleware(
            {"type": "http", "path": "/api/probe", "headers": headers},
            receive,
            send,
        )
    )
    return sent, forwarded_body, received, called


@pytest.fixture
def json_headers() -> list[tuple[bytes, bytes]]:
    return [
        (b"authorization", b"Bearer secret-token"),
        (b"content-type", b"application/json"),
    ]


def test_content_length_over_limit_is_rejected_before_receive(
    monkeypatch: pytest.MonkeyPatch,
    json_headers: list[tuple[bytes, bytes]],
) -> None:
    sent, _body, received, called = run_request(
        monkeypatch,
        headers=[*json_headers, (b"content-length", b"9")],
        request_messages=[],
    )
    assert sent[0]["status"] == 413
    assert received == 0
    assert not called


@pytest.mark.parametrize("content_length", [b"invalid", b"9" * 5000])
def test_invalid_content_length_is_rejected_without_reading_body(
    monkeypatch: pytest.MonkeyPatch,
    json_headers: list[tuple[bytes, bytes]],
    content_length: bytes,
) -> None:
    sent, _body, received, called = run_request(
        monkeypatch,
        headers=[*json_headers, (b"content-length", content_length)],
        request_messages=[],
    )
    assert sent[0]["status"] == 400
    assert received == 0
    assert not called


def test_chunked_json_over_limit_is_rejected_before_downstream(
    monkeypatch: pytest.MonkeyPatch,
    json_headers: list[tuple[bytes, bytes]],
) -> None:
    sent, _body, received, called = run_request(
        monkeypatch,
        headers=json_headers,
        request_messages=[
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"6789", "more_body": False},
        ],
    )
    assert sent[0]["status"] == 413
    assert received == 2
    assert not called


def test_chunked_json_at_limit_replays_original_body(
    monkeypatch: pytest.MonkeyPatch,
    json_headers: list[tuple[bytes, bytes]],
) -> None:
    sent, body, _received, called = run_request(
        monkeypatch,
        headers=json_headers,
        request_messages=[
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"5678", "more_body": False},
        ],
    )
    assert sent[0]["status"] == 200
    assert b"".join(body) == b"12345678"
    assert called


def test_json_without_content_type_is_still_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    sent, _body, received, called = run_request(
        monkeypatch,
        headers=[(b"authorization", b"Bearer secret-token")],
        request_messages=[{"type": "http.request", "body": b"123456789", "more_body": False}],
    )
    assert sent[0]["status"] == 413
    assert received == 1
    assert not called


def test_non_json_content_type_cannot_bypass_business_body_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent, _body, _received, called = run_request(
        monkeypatch,
        headers=[
            (b"authorization", b"Bearer secret-token"),
            (b"content-type", b"multipart/form-data; boundary=x"),
        ],
        request_messages=[{"type": "http.request", "body": b"123456789", "more_body": False}],
    )
    assert sent[0]["status"] == 413
    assert not called


def test_auth_rejection_does_not_read_request_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", "secret-token")
    sent: list[dict[str, Any]] = []
    called = False

    async def app(_scope, _receive, _send) -> None:
        nonlocal called
        called = True

    async def receive() -> dict[str, Any]:
        pytest.fail("unauthenticated body must not be read")

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(
        APIRequestBoundaryMiddleware(app)(
            {"type": "http", "path": "/v1/probe", "headers": []},
            receive,
            send,
        )
    )
    assert sent[0]["status"] == 401
    assert not called


def test_health_alias_is_not_authenticated_or_body_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", "")
    called = False

    async def app(_scope, _receive, _send) -> None:
        nonlocal called
        called = True

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"too large", "more_body": False}

    async def send(_message: dict[str, Any]) -> None:
        pass

    asyncio.run(
        APIRequestBoundaryMiddleware(app)(
            {"type": "http", "path": "/api/health", "headers": [(b"content-type", b"application/json")]},
            receive,
            send,
        )
    )
    assert called
