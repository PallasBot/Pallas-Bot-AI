"""AI HTTP API Bearer 鉴权（与 Bot ai_extension.token 对齐）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)


def require_api_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> None:
    expected = (settings.api_bearer_token or "").strip()
    if not expected:
        return
    if credentials is None or (credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=401, detail="缺少 Authorization Bearer")
    if (credentials.credentials or "") != expected:
        raise HTTPException(status_code=401, detail="Authorization Bearer 无效")
