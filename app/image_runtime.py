from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.core.logger import logger
from app.image_reference import artifact_from_upstream_json, download_reference_blobs
from app.schemas.image_api import (
    ImageArtifact,
    ImageBackendStatus,
    ImageGenerateRequest,
    ImageGenerateResponse,
    ImageRuntimeStatus,
    RuntimeErrorBody,
)


@dataclass
class ImageBackendRuntimeState:
    health_state: str = "unknown"
    circuit_state: str = "closed"
    consecutive_failures: int = 0
    circuit_open_until: float = 0.0
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_latency_ms: int | None = None
    recent_failure_class: str | None = None


class ImageBackendSpec:
    def __init__(
        self,
        *,
        backend_id: str,
        provider_id: str,
        base_url: str,
        api_key: str,
        model: str,
        enabled: bool = True,
    ) -> None:
        self.backend_id = backend_id
        self.provider_id = provider_id
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.enabled = enabled

    def is_configured(self) -> bool:
        return self.enabled and bool(self.base_url.strip()) and bool(self.api_key.strip()) and bool(self.model.strip())


_IMAGE_BACKEND_STATE = ImageBackendRuntimeState()


def clear_image_runtime_state() -> None:
    _IMAGE_BACKEND_STATE.health_state = "unknown"
    _IMAGE_BACKEND_STATE.circuit_state = "closed"
    _IMAGE_BACKEND_STATE.consecutive_failures = 0
    _IMAGE_BACKEND_STATE.circuit_open_until = 0.0
    _IMAGE_BACKEND_STATE.last_success_at = None
    _IMAGE_BACKEND_STATE.last_failure_at = None
    _IMAGE_BACKEND_STATE.last_latency_ms = None
    _IMAGE_BACKEND_STATE.recent_failure_class = None


def record_image_success(*, latency_ms: int | None) -> None:
    _IMAGE_BACKEND_STATE.health_state = "healthy"
    _IMAGE_BACKEND_STATE.circuit_state = "closed"
    _IMAGE_BACKEND_STATE.consecutive_failures = 0
    _IMAGE_BACKEND_STATE.circuit_open_until = 0.0
    _IMAGE_BACKEND_STATE.last_success_at = time.monotonic()
    _IMAGE_BACKEND_STATE.last_latency_ms = latency_ms
    _IMAGE_BACKEND_STATE.recent_failure_class = None


def record_image_failure(*, failure_class: str) -> None:
    now = time.monotonic()
    _IMAGE_BACKEND_STATE.health_state = "degraded"
    _IMAGE_BACKEND_STATE.consecutive_failures += 1
    _IMAGE_BACKEND_STATE.last_failure_at = now
    _IMAGE_BACKEND_STATE.recent_failure_class = failure_class
    if _IMAGE_BACKEND_STATE.consecutive_failures >= settings.image_open_circuit_failures:
        _IMAGE_BACKEND_STATE.circuit_state = "open"
        _IMAGE_BACKEND_STATE.circuit_open_until = now + settings.image_circuit_cooldown_sec


def effective_circuit_state(now: float | None = None) -> str:
    current = time.monotonic() if now is None else now
    if _IMAGE_BACKEND_STATE.circuit_state == "open" and _IMAGE_BACKEND_STATE.circuit_open_until <= current:
        _IMAGE_BACKEND_STATE.circuit_state = "half_open"
    return _IMAGE_BACKEND_STATE.circuit_state


def load_image_backend() -> ImageBackendSpec:
    return ImageBackendSpec(
        backend_id="image-primary",
        provider_id="image-gateway",
        base_url=str(settings.image_base_url or "").strip(),
        api_key=str(settings.image_api_key or "").strip(),
        model=str(settings.image_model or "").strip(),
        enabled=bool(settings.image_enabled),
    )


def image_runtime_status() -> ImageRuntimeStatus:
    backend = load_image_backend()
    configured = backend.is_configured()
    health_state = _IMAGE_BACKEND_STATE.health_state if configured else "unknown"
    circuit_state = effective_circuit_state()
    degraded_state = "degraded" if circuit_state == "open" else "normal"
    if circuit_state == "open":
        health_state = "degraded"
    return ImageRuntimeStatus(
        health_state=health_state,
        degraded_state=degraded_state,
        queue_depth=0,
        active_requests=0,
        active_tasks=0,
        recent_success_rate=None,
        backends=[
            ImageBackendStatus(
                backend_id=backend.backend_id,
                provider_id=backend.provider_id,
                health_state=health_state,
                circuit_state=circuit_state,
                last_latency_ms=_IMAGE_BACKEND_STATE.last_latency_ms,
                consecutive_failures=_IMAGE_BACKEND_STATE.consecutive_failures,
                recent_failure_class=_IMAGE_BACKEND_STATE.recent_failure_class,
            )
        ],
    )


def image_edits_url(base_url: str) -> str:
    root = base_url.strip().rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/images/edits"
    return f"{root}/v1/images/edits"


def image_generate_url(base_url: str) -> str:
    root = base_url.strip().rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/images/generations"
    return f"{root}/v1/images/generations"


def generation_json_payload(*, model: str, prompt: str) -> dict[str, object]:
    payload: dict[str, object] = {"model": model, "prompt": prompt}
    if not settings.image_omit_response_format:
        payload["response_format"] = "b64_json"
    return payload


def edits_multipart_fields(*, model: str, prompt: str) -> dict[str, str]:
    data: dict[str, str] = {"model": model, "prompt": prompt}
    if not settings.image_omit_response_format:
        data["response_format"] = "b64_json"
    return data


def edits_multipart_files(ref_blobs: list[bytes]) -> list[tuple[str, tuple[str, bytes, str]]]:
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for index, blob in enumerate(ref_blobs):
        files.append(("image", (f"ref_{index}.png", blob, "image/png")))
    return files


async def post_image_generations(
    client: httpx.AsyncClient,
    *,
    backend: ImageBackendSpec,
    prompt: str,
    timeout_sec: float,
) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {backend.api_key}",
        "Content-Type": "application/json",
    }
    url = image_generate_url(backend.base_url)
    payload = generation_json_payload(model=backend.model, prompt=prompt)
    return await client.post(url, json=payload, headers=headers, timeout=httpx.Timeout(timeout_sec))


async def post_image_edits(
    client: httpx.AsyncClient,
    *,
    backend: ImageBackendSpec,
    prompt: str,
    ref_blobs: list[bytes],
    timeout_sec: float,
) -> httpx.Response:
    headers = {"Authorization": f"Bearer {backend.api_key}"}
    url = image_edits_url(backend.base_url)
    return await client.post(
        url,
        headers=headers,
        files=edits_multipart_files(ref_blobs),
        data=edits_multipart_fields(model=backend.model, prompt=prompt),
        timeout=httpx.Timeout(timeout_sec, connect=min(30.0, timeout_sec)),
    )


async def submit_image_generate(body: ImageGenerateRequest) -> ImageGenerateResponse:
    if effective_circuit_state() == "open":
        backend = load_image_backend()
        return ImageGenerateResponse(
            request_id=body.request_id,
            result_state="failed",
            provider_id=backend.provider_id,
            backend_id=backend.backend_id,
            error=RuntimeErrorBody(
                code="image_circuit_open",
                message="image runtime circuit is open",
                retryable=True,
                failure_class="runtime_overloaded",
            ),
        )
    if not body.payload.prompt.strip():
        return ImageGenerateResponse(
            request_id=body.request_id,
            result_state="failed",
            provider_id="image-gateway",
            backend_id="image-primary",
            error=RuntimeErrorBody(
                code="invalid_prompt",
                message="prompt is empty",
                retryable=False,
                failure_class="invalid_upstream_response",
            ),
        )
    backend = load_image_backend()
    if not backend.is_configured():
        return ImageGenerateResponse(
            request_id=body.request_id,
            result_state="failed",
            provider_id=backend.provider_id,
            backend_id=backend.backend_id,
            error=RuntimeErrorBody(
                code="image_backend_not_configured",
                message="image backend is not configured",
                retryable=False,
                failure_class="provider_unavailable",
            ),
        )

    ref_urls = list(body.payload.reference_urls or [])
    timeout_sec = body.policy.timeout_sec or settings.image_request_timeout
    ref_timeout = min(settings.image_ref_download_timeout, timeout_sec)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec)) as client:
            ref_blobs = await download_reference_blobs(client, ref_urls, timeout_sec=ref_timeout)
            if ref_urls and not ref_blobs:
                logger.warning(
                    "image runtime ref download empty request_id={} requested={}",
                    body.request_id,
                    len(ref_urls),
                )
            elif ref_urls and len(ref_blobs) < len(ref_urls):
                logger.warning(
                    "image runtime ref download partial request_id={} requested={} got={}",
                    body.request_id,
                    len(ref_urls),
                    len(ref_blobs),
                )
            if ref_blobs:
                response = await post_image_edits(
                    client,
                    backend=backend,
                    prompt=body.payload.prompt,
                    ref_blobs=ref_blobs,
                    timeout_sec=timeout_sec,
                )
            else:
                response = await post_image_generations(
                    client,
                    backend=backend,
                    prompt=body.payload.prompt,
                    timeout_sec=timeout_sec,
                )

            if response.status_code != 200:
                logger.warning(
                    "image runtime backend failed backend={} status={} body={}",
                    backend.backend_id,
                    response.status_code,
                    response.text[:500],
                )
                failure_class = "provider_unavailable" if response.status_code >= 500 else "invalid_upstream_response"
                return ImageGenerateResponse(
                    request_id=body.request_id,
                    result_state="failed",
                    provider_id=backend.provider_id,
                    backend_id=backend.backend_id,
                    error=RuntimeErrorBody(
                        code=f"image_status_{response.status_code}",
                        message=f"image backend status {response.status_code}",
                        retryable=response.status_code >= 500,
                        failure_class=failure_class,
                    ),
                )

            try:
                data = response.json()
                artifact: ImageArtifact = await artifact_from_upstream_json(
                    client,
                    data,
                    timeout_sec=ref_timeout,
                )
            except (ValueError, TypeError) as exc:
                logger.warning("image runtime invalid response backend={} err={}", backend.backend_id, exc)
                return ImageGenerateResponse(
                    request_id=body.request_id,
                    result_state="failed",
                    provider_id=backend.provider_id,
                    backend_id=backend.backend_id,
                    error=RuntimeErrorBody(
                        code="image_invalid_response",
                        message="image backend returned invalid response",
                        retryable=False,
                        failure_class="invalid_upstream_response",
                    ),
                )
    except httpx.TimeoutException:
        return ImageGenerateResponse(
            request_id=body.request_id,
            result_state="failed",
            provider_id=backend.provider_id,
            backend_id=backend.backend_id,
            error=RuntimeErrorBody(
                code="image_timeout",
                message="image generation timed out",
                retryable=True,
                failure_class="timeout",
            ),
        )
    except httpx.ConnectError:
        return ImageGenerateResponse(
            request_id=body.request_id,
            result_state="failed",
            provider_id=backend.provider_id,
            backend_id=backend.backend_id,
            error=RuntimeErrorBody(
                code="image_connect_error",
                message="image backend connect failed",
                retryable=True,
                failure_class="connect_error",
            ),
        )
    except httpx.HTTPError as exc:
        logger.warning("image runtime http error backend={} err={}", backend.backend_id, exc)
        return ImageGenerateResponse(
            request_id=body.request_id,
            result_state="failed",
            provider_id=backend.provider_id,
            backend_id=backend.backend_id,
            error=RuntimeErrorBody(
                code="image_http_error",
                message="image backend http error",
                retryable=True,
                failure_class="internal_error",
            ),
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    return ImageGenerateResponse(
        request_id=body.request_id,
        result_state="success",
        provider_id=backend.provider_id,
        backend_id=backend.backend_id,
        latency_ms=latency_ms,
        data=artifact,
    )
