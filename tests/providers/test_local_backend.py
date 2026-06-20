from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.core.config import Settings
from app.providers.local_backend import complete_local_message, resolve_local_provider
from app.providers.registry import clear_provider_registry_cache, load_provider_registry, local_base_url_for_spec


@pytest.fixture(autouse=True)
def reset_registry_cache() -> None:
    clear_provider_registry_cache()
    yield
    clear_provider_registry_cache()


def test_resolve_local_provider_uses_custom_base_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    providers_file = config_dir / "providers.toml"
    providers_file.write_text(
        """
[[providers]]
id = "local"
kind = "local"

[[providers]]
id = "ollama-tools"
kind = "local"
base_url = "http://127.0.0.1:11435"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    load_provider_registry(Settings(llm_providers_file=str(providers_file)))
    pid, spec, base_url = resolve_local_provider("ollama-tools")
    assert pid == "ollama-tools"
    assert base_url == "http://127.0.0.1:11435"
    assert local_base_url_for_spec(spec) == "http://127.0.0.1:11435"


def test_complete_local_message_posts_to_provider_base_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    providers_file = config_dir / "providers.toml"
    providers_file.write_text(
        """
[[providers]]
id = "ollama-tools"
kind = "local"
base_url = "http://127.0.0.1:11435"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    load_provider_registry(Settings(llm_providers_file=str(providers_file)))

    captured: dict[str, str] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"message": {"role": "assistant", "content": "ok"}}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, json: dict) -> FakeResponse:
            captured["url"] = url
            captured["model"] = str(json.get("model"))
            return FakeResponse()

    monkeypatch.setattr("app.providers.local_backend.httpx.AsyncClient", FakeClient)
    # 本测试只验证 HTTP 路由，不涉及 GPU；关掉 LLM GPU 锁避免连真实 redis。
    monkeypatch.setattr("app.providers.local_backend.settings.gpu_lock_llm_enabled", False)

    async def run() -> dict:
        return await complete_local_message(
            [{"role": "user", "content": "hi"}],
            model="tiny",
            options={},
            provider_id="ollama-tools",
        )

    message = asyncio.run(run())
    assert message["content"] == "ok"
    assert captured["url"] == "http://127.0.0.1:11435/api/chat"
    assert captured["model"] == "tiny"
