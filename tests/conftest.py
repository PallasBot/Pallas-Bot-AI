from __future__ import annotations

import pytest

from app.providers.registry import clear_provider_registry_cache


@pytest.fixture(autouse=True)
def reset_provider_registry_cache() -> None:
    clear_provider_registry_cache()
    yield
    clear_provider_registry_cache()
