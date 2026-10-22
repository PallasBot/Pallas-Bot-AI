"""AI HTTP API Bearer 鉴权（与 Bot ai_extension.token 对齐）。"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)


def validate_api_bearer_token(token: bytes | str | None) -> int | None:
    expected = (settings.api_bearer_token or "").strip()
    if not expected:
        return 503
    if token is None:
        return 401
    supplied = token.encode("utf-8") if isinstance(token, str) else token
    return None if hmac.compare_digest(supplied, expected.encode("utf-8")) else 401


def validate_api_bearer_header(values: list[bytes]) -> int | None:
    if not (settings.api_bearer_token or "").strip():
        return 503
    if len(values) != 1:
        return 401
    scheme, separator, token = values[0].partition(b" ")
    if scheme.lower() != b"bearer" or not separator or not token or any(byte in b" \t\r\n" for byte in token):
        return 401
    return validate_api_bearer_token(token)


def _raise_auth_error(status_code: int) -> None:
    if status_code == 503:
        raise HTTPException(status_code=503, detail="Service authentication is not configured")
    raise HTTPException(status_code=401, detail="Invalid or missing Bearer token")


def require_api_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> None:
    token = credentials.credentials if credentials is not None and credentials.scheme.lower() == "bearer" else None
    status_code = validate_api_bearer_token(token)
    if status_code is not None:
        _raise_auth_error(status_code)


def require_configured_api_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> None:
    require_api_bearer_token(credentials)
