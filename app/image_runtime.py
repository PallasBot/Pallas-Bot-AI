from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logger import logger
from app.image_reference import artifact_from_upstream_json, download_reference_blobs
from app.schemas.image_api import (
    ImageArtifact,
    ImageBackendStatus,
    ImageGeneratePayload,
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
        omit_response_format: bool | None = None,
        from_request: bool = False,
    ) -> None:
        self.backend_id = backend_id
        self.provider_id = provider_id
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.enabled = enabled
        self.omit_response_format = omit_response_format
        self.from_request = from_request

    def is_configured(self) -> bool:
        # model 可空：部分网关不要求；与 Bot 插件主网关行为对齐
        return self.enabled and bool(self.base_url.strip()) and bool(self.api_key.strip())

    def log_host(self) -> str:
        host = urlparse(self.base_url.strip()).netloc.strip()
        return host or self.backend_id


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
        omit_response_format=bool(settings.image_omit_response_format),
        from_request=False,
    )


def backends_from_payload(payload: ImageGeneratePayload) -> list[ImageBackendSpec]:
    gateway = payload.gateway
    if gateway is None or not gateway.backends:
        return []
    out: list[ImageBackendSpec] = []
    for index, row in enumerate(gateway.backends):
        base_url = str(row.base_url or "").strip()
        api_key = str(row.api_key or "").strip()
        if not base_url or not api_key:
            continue
        name = str(row.name or "").strip()
        backend_id = f"req-{index}" if not name else f"req-{index}-{name}"[:64]
        out.append(
            ImageBackendSpec(
                backend_id=backend_id,
                provider_id="bot-gateway",
                base_url=base_url,
                api_key=api_key,
                model=str(row.model or "").strip(),
                enabled=True,
                omit_response_format=bool(row.omit_response_format),
                from_request=True,
            )
        )
    return out


def resolve_image_backends(body: ImageGenerateRequest) -> list[ImageBackendSpec]:
    requested = backends_from_payload(body.payload)
    if requested:
        return requested
    return [load_image_backend()]


def payload_has_request_gateway(payload: ImageGeneratePayload | dict | None) -> bool:
    if payload is None:
        return False
    if isinstance(payload, dict):
        try:
            payload = ImageGeneratePayload.model_validate(payload)
        except Exception:
            return False
    return bool(backends_from_payload(payload))


def image_runtime_feature_allowed(payload: ImageGeneratePayload | dict | None = None) -> bool:
    if settings.image_enabled:
        return True
    return payload_has_request_gateway(payload)


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


def generation_json_payload(*, model: str, prompt: str, omit_response_format: bool) -> dict[str, object]:
    payload: dict[str, object] = {"model": model, "prompt": prompt}
    if not omit_response_format:
        payload["response_format"] = "b64_json"
    return payload


def edits_multipart_fields(*, model: str, prompt: str, omit_response_format: bool) -> dict[str, str]:
    data: dict[str, str] = {"model": model, "prompt": prompt}
    if not omit_response_format:
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
    omit = (
        bool(settings.image_omit_response_format)
        if backend.omit_response_format is None
        else bool(backend.omit_response_format)
    )
    payload = generation_json_payload(
        model=backend.model,
        prompt=prompt,
        omit_response_format=omit,
    )
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
    omit = (
        bool(settings.image_omit_response_format)
        if backend.omit_response_format is None
        else bool(backend.omit_response_format)
    )
    return await client.post(
        url,
        headers=headers,
        files=edits_multipart_files(ref_blobs),
        data=edits_multipart_fields(
            model=backend.model,
            prompt=prompt,
            omit_response_format=omit,
        ),
        timeout=httpx.Timeout(timeout_sec, connect=min(30.0, timeout_sec)),
    )


def _failed_response(
    *,
    request_id: str,
    backend: ImageBackendSpec,
    code: str,
    message: str,
    retryable: bool,
    failure_class: str,
) -> ImageGenerateResponse:
    return ImageGenerateResponse(
        request_id=request_id,
        result_state="failed",
        provider_id=backend.provider_id,
        backend_id=backend.backend_id,
        error=RuntimeErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            failure_class=failure_class,  # type: ignore[arg-type]
        ),
    )


async def _attempt_backend(
    client: httpx.AsyncClient,
    *,
    body: ImageGenerateRequest,
    backend: ImageBackendSpec,
    ref_blobs: list[bytes],
    timeout_sec: float,
    ref_timeout: float,
) -> ImageGenerateResponse:
    try:
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
                "image runtime backend failed backend={} host={} status={} body={}",
                backend.backend_id,
                backend.log_host(),
                response.status_code,
                response.text[:500],
            )
            failure_class = "provider_unavailable" if response.status_code >= 500 else "invalid_upstream_response"
            return _failed_response(
                request_id=body.request_id,
                backend=backend,
                code=f"image_status_{response.status_code}",
                message=f"image backend status {response.status_code}",
                retryable=response.status_code >= 500,
                failure_class=failure_class,
            )

        try:
            data = response.json()
            artifact: ImageArtifact = await artifact_from_upstream_json(
                client,
                data,
                timeout_sec=ref_timeout,
            )
        except (ValueError, TypeError) as exc:
            logger.warning(
                "image runtime invalid response backend={} host={} err={}",
                backend.backend_id,
                backend.log_host(),
                exc,
            )
            return _failed_response(
                request_id=body.request_id,
                backend=backend,
                code="image_invalid_response",
                message="image backend returned invalid response",
                retryable=False,
                failure_class="invalid_upstream_response",
            )
    except httpx.TimeoutException:
        return _failed_response(
            request_id=body.request_id,
            backend=backend,
            code="image_timeout",
            message="image generation timed out",
            retryable=True,
            failure_class="timeout",
        )
    except httpx.ConnectError:
        return _failed_response(
            request_id=body.request_id,
            backend=backend,
            code="image_connect_error",
            message="image backend connect failed",
            retryable=True,
            failure_class="connect_error",
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "image runtime http error backend={} host={} err={}",
            backend.backend_id,
            backend.log_host(),
            exc,
        )
        return _failed_response(
            request_id=body.request_id,
            backend=backend,
            code="image_http_error",
            message="image backend http error",
            retryable=True,
            failure_class="internal_error",
        )

    return ImageGenerateResponse(
        request_id=body.request_id,
        result_state="success",
        provider_id=backend.provider_id,
        backend_id=backend.backend_id,
        data=artifact,
    )


async def submit_image_generate(body: ImageGenerateRequest) -> ImageGenerateResponse:
    backends = resolve_image_backends(body)
    use_request_gateway = any(item.from_request for item in backends)

    if not use_request_gateway and effective_circuit_state() == "open":
        backend = backends[0] if backends else load_image_backend()
        return _failed_response(
            request_id=body.request_id,
            backend=backend,
            code="image_circuit_open",
            message="image runtime circuit is open",
            retryable=True,
            failure_class="runtime_overloaded",
        )
    if not body.payload.prompt.strip():
        backend = backends[0] if backends else load_image_backend()
        return _failed_response(
            request_id=body.request_id,
            backend=backend,
            code="invalid_prompt",
            message="prompt is empty",
            retryable=False,
            failure_class="invalid_upstream_response",
        )

    configured = [item for item in backends if item.is_configured()]
    if not configured:
        backend = backends[0] if backends else load_image_backend()
        return _failed_response(
            request_id=body.request_id,
            backend=backend,
            code="image_backend_not_configured",
            message="image backend is not configured",
            retryable=False,
            failure_class="provider_unavailable",
        )

    ref_urls = list(body.payload.reference_urls or [])
    timeout_sec = body.policy.timeout_sec or settings.image_request_timeout
    ref_timeout = min(settings.image_ref_download_timeout, timeout_sec)
    started = time.perf_counter()
    last_failure: ImageGenerateResponse | None = None

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

        for index, backend in enumerate(configured):
            logger.info(
                "image runtime try backend={} host={} index={}/{}",
                backend.backend_id,
                backend.log_host(),
                index + 1,
                len(configured),
            )
            result = await _attempt_backend(
                client,
                body=body,
                backend=backend,
                ref_blobs=ref_blobs,
                timeout_sec=timeout_sec,
                ref_timeout=ref_timeout,
            )
            if result.result_state == "success":
                latency_ms = int((time.perf_counter() - started) * 1000)
                result.latency_ms = latency_ms
                return result
            last_failure = result
            if index < len(configured) - 1:
                logger.info(
                    "image runtime switching backend after failure backend={} host={} code={}",
                    backend.backend_id,
                    backend.log_host(),
                    (result.error.code if result.error else "unknown"),
                )

    return last_failure or _failed_response(
        request_id=body.request_id,
        backend=configured[0],
        code="image_all_backends_failed",
        message="all image backends failed",
        retryable=True,
        failure_class="provider_unavailable",
    )
