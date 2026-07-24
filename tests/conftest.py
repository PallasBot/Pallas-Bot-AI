from __future__ import annotations

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def isolate_api_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "api_bearer_token", "")
