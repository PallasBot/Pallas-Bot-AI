from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import settings
from app.http.deps.api_auth import validate_api_bearer_header

ASGIMessage = dict[str, Any]
Receive = Callable[[], Awaitable[ASGIMessage]]
Send = Callable[[ASGIMessage], Awaitable[None]]


class APIRequestBoundaryMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._is_business_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return

        headers = scope.get("headers", [])
        authorization = [value for name, value in headers if name.lower() == b"authorization"]
        auth_status = validate_api_bearer_header(authorization)
        if auth_status is not None:
            await self._respond(send, auth_status)
            return

        # Business body routes accept JSON; a mismatched Content-Type must not bypass the cap.
        max_bytes = settings.api_max_request_bytes
        content_lengths = [value for name, value in headers if name.lower() == b"content-length"]
        if len(content_lengths) > 1:
            await self._respond(send, 400, "Invalid Content-Length")
            return
        if content_lengths:
            raw_length = content_lengths[0]
            if not raw_length.isdigit():
                await self._respond(send, 400, "Invalid Content-Length")
                return
            try:
                content_length = int(raw_length)
            except ValueError:
                await self._respond(send, 400, "Invalid Content-Length")
                return
            if content_length > max_bytes:
                await self._respond(send, 413, "Request body too large")
                return

        messages: list[ASGIMessage] = []
        received_bytes = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                messages.append(message)
                break
            if message["type"] != "http.request":
                continue
            received_bytes += len(message.get("body", b""))
            if received_bytes > max_bytes:
                await self._respond(send, 413, "Request body too large")
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        message_index = 0

        async def replay_receive() -> ASGIMessage:
            nonlocal message_index
            if message_index < len(messages):
                message = messages[message_index]
                message_index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    def _is_business_path(path: str) -> bool:
        return (
            (path == "/api" or path.startswith("/api/") and path != "/api/health")
            or path == "/v1"
            or path.startswith("/v1/")
        )

    @staticmethod
    async def _respond(send: Send, status: int, detail: str | None = None) -> None:
        if detail is None:
            detail = "Service authentication is not configured" if status == 503 else "Invalid or missing Bearer token"
        if status == 413:
            detail = "Request body too large"
        body = json.dumps({"detail": detail}, separators=(",", ":")).encode("utf-8")
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode("ascii"))]
        if status == 401:
            headers.append((b"www-authenticate", b"Bearer"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
