from __future__ import annotations

import asyncio
import base64

import pytest

from app.core.config import settings
from app.image_reference import (
    artifact_from_upstream_json,
    decode_inline_image_reference,
    download_reference_blob,
    download_reference_blobs,
    extract_image_fields,
    is_platform_reference_url,
    reference_request_headers,
)
from app.image_runtime import clear_image_runtime_state, submit_image_generate
from app.schemas.image_api import (
    ImageGatewayBackend,
    ImageGatewaySpec,
    ImageGeneratePayload,
    ImageGenerateRequest,
    RuntimeCaller,
    RuntimePolicy,
)

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADU0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")


@pytest.fixture(autouse=True)
def reset_image_runtime_state() -> None:
    clear_image_runtime_state()
    yield
    clear_image_runtime_state()


def test_decode_inline_image_reference() -> None:
    inline = f"data:image/png;base64,{PNG_B64}"
    assert decode_inline_image_reference(inline) == PNG_BYTES
    assert decode_inline_image_reference("not-a-url") is None


def test_reference_request_headers_adds_referer_for_qq_cdn() -> None:
    headers = reference_request_headers("https://multimedia.nt.qq.com.cn/download/abc")
    assert headers["Referer"] == "https://qun.qq.com/"
    assert headers["User-Agent"]


def test_is_platform_reference_url() -> None:
    assert is_platform_reference_url("https://gchat.qpic.cn/download/abc")
    assert not is_platform_reference_url("https://cdn.example.com/ref.png")


def test_extract_image_fields_from_b64_json() -> None:
    url, b64 = extract_image_fields({"data": [{"b64_json": PNG_B64}]})
    assert url is None
    assert b64 == PNG_B64


def test_extract_image_fields_from_url() -> None:
    url, b64 = extract_image_fields({"data": [{"url": "https://example.com/out.png"}]})
    assert url == "https://example.com/out.png"
    assert b64 is None


def test_submit_image_generate_uses_edits_when_refs_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    monkeypatch.setattr(settings, "image_base_url", "https://image.example.com")
    monkeypatch.setattr(settings, "image_api_key", "secret")
    monkeypatch.setattr(settings, "image_model", "gpt-image-1")
    monkeypatch.setattr(settings, "image_omit_response_format", True)

    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        content = PNG_BYTES

        def json(self) -> dict:
            return {"data": [{"b64_json": PNG_B64}]}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, url: str, **kwargs) -> FakeResponse:
            captured["ref_url"] = url
            return FakeResponse()

        async def post(self, url: str, **kwargs) -> FakeResponse:
            captured["post_url"] = url
            captured["post_kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr("app.image_runtime.httpx.AsyncClient", FakeClient)

    body = ImageGenerateRequest(
        request_id="req-edits",
        caller=RuntimeCaller(source="bot", bot_id=1, plugin="pallas_plugin_draw"),
        policy=RuntimePolicy(),
        payload=ImageGeneratePayload(
            prompt="一只羊",
            reference_urls=["https://cdn.example.com/ref.png"],
        ),
    )

    result = asyncio.run(submit_image_generate(body))
    assert result.result_state == "success"
    assert result.data is not None
    assert result.data.b64_data == PNG_B64
    assert captured["post_url"] == "https://image.example.com/v1/images/edits"
    post_kwargs = captured["post_kwargs"]
    assert isinstance(post_kwargs, dict)
    assert "files" in post_kwargs
    assert "json" not in post_kwargs


def test_submit_image_generate_uses_generations_without_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    monkeypatch.setattr(settings, "image_base_url", "https://image.example.com/v1")
    monkeypatch.setattr(settings, "image_api_key", "secret")
    monkeypatch.setattr(settings, "image_model", "gpt-image-1")

    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"data": [{"b64_json": PNG_B64}]}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, **kwargs) -> FakeResponse:
            captured["post_url"] = url
            captured["post_kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr("app.image_runtime.httpx.AsyncClient", FakeClient)

    body = ImageGenerateRequest(
        request_id="req-gen",
        caller=RuntimeCaller(source="bot", bot_id=1, plugin="pallas_plugin_draw"),
        policy=RuntimePolicy(),
        payload=ImageGeneratePayload(prompt="一只羊", reference_urls=[]),
    )

    result = asyncio.run(submit_image_generate(body))
    assert result.result_state == "success"
    assert captured["post_url"] == "https://image.example.com/v1/images/generations"
    post_kwargs = captured["post_kwargs"]
    assert isinstance(post_kwargs, dict)
    assert "json" in post_kwargs
    assert "files" not in post_kwargs


def test_artifact_from_upstream_json_downloads_url() -> None:
    class FakeResponse:
        status_code = 200
        content = PNG_BYTES

    class FakeClient:
        async def get(self, url: str, **kwargs) -> FakeResponse:
            assert url == "https://example.com/out.png"
            return FakeResponse()

    async def run():
        return await artifact_from_upstream_json(
            FakeClient(),  # type: ignore[arg-type]
            {"data": [{"url": "https://example.com/out.png"}]},
            timeout_sec=30.0,
        )

    artifact = asyncio.run(run())
    assert artifact.b64_data == PNG_B64


def test_download_reference_blob_rejects_platform_url() -> None:
    class FakeClient:
        async def get(self, url: str, **kwargs) -> object:
            raise AssertionError("platform url must not be fetched on AI side")

    async def run() -> bytes | None:
        return await download_reference_blob(
            FakeClient(),  # type: ignore[arg-type]
            "https://gchat.qpic.cn/download/abc",
            timeout_sec=30.0,
        )

    assert asyncio.run(run()) is None


def test_download_reference_blobs_inline() -> None:
    inline = f"data:image/png;base64,{PNG_B64}"

    class FakeClient:
        pass

    async def run() -> list[bytes]:
        return await download_reference_blobs(FakeClient(), [inline], timeout_sec=30.0)  # type: ignore[arg-type]

    blobs = asyncio.run(run())
    assert blobs == [PNG_BYTES]


def test_submit_image_generate_uses_request_gateway_not_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", True)
    monkeypatch.setattr(settings, "image_base_url", "https://packy.example.com")
    monkeypatch.setattr(settings, "image_api_key", "packy-key")
    monkeypatch.setattr(settings, "image_model", "packy-model")

    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"data": [{"b64_json": PNG_B64}]}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, **kwargs) -> FakeResponse:
            captured["post_url"] = url
            return FakeResponse()

    monkeypatch.setattr("app.image_runtime.httpx.AsyncClient", FakeClient)

    body = ImageGenerateRequest(
        request_id="req-gw",
        caller=RuntimeCaller(source="bot", bot_id=1, plugin="draw"),
        policy=RuntimePolicy(),
        payload=ImageGeneratePayload(
            prompt="一只羊",
            reference_urls=[],
            gateway=ImageGatewaySpec(
                backends=[
                    ImageGatewayBackend(
                        base_url="https://aigateway.example/",
                        api_key="sk-bot",
                        model="gpt-image-2",
                    )
                ]
            ),
        ),
    )
    result = asyncio.run(submit_image_generate(body))
    assert result.result_state == "success"
    assert captured["post_url"] == "https://aigateway.example/v1/images/generations"
    assert result.provider_id == "bot-gateway"


def test_submit_image_generate_falls_through_request_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "image_enabled", False)
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code
            self.text = "err"

        def json(self) -> dict:
            return {"data": [{"b64_json": PNG_B64}]}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, **kwargs) -> FakeResponse:
            calls.append(url)
            if "bad.example" in url:
                return FakeResponse(500)
            return FakeResponse(200)

    monkeypatch.setattr("app.image_runtime.httpx.AsyncClient", FakeClient)

    body = ImageGenerateRequest(
        request_id="req-fb",
        caller=RuntimeCaller(source="bot", bot_id=1, plugin="draw"),
        policy=RuntimePolicy(),
        payload=ImageGeneratePayload(
            prompt="一只羊",
            gateway=ImageGatewaySpec(
                backends=[
                    ImageGatewayBackend(base_url="https://bad.example/", api_key="a", model="m1"),
                    ImageGatewayBackend(base_url="https://good.example/", api_key="b", model="m2"),
                ]
            ),
        ),
    )
    result = asyncio.run(submit_image_generate(body))
    assert result.result_state == "success"
    assert calls == [
        "https://bad.example/v1/images/generations",
        "https://good.example/v1/images/generations",
    ]
    assert result.backend_id.startswith("req-1")
