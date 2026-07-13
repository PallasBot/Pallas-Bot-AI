from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.api_errors import IMAGE_RUNTIME_DISABLED
from app.image_runtime import (
    image_runtime_feature_allowed,
    image_runtime_status,
    record_image_failure,
    record_image_success,
    resolve_image_backends,
    submit_image_generate,
)
from app.media_task_runtime import submit_media_task
from app.schemas.image_api import (
    ImageGenerateRequest,
    ImageGenerateResponse,
    ImageRuntimeStatus,
    RuntimeErrorBody,
)
from app.schemas.media_task_api import MediaTaskSubmitRequest

router = APIRouter()


@router.post("/images/generate", response_model=ImageGenerateResponse)
async def post_image_generate(body: ImageGenerateRequest) -> ImageGenerateResponse:
    if not image_runtime_feature_allowed(body.payload):
        raise HTTPException(status_code=503, detail=IMAGE_RUNTIME_DISABLED)
    if body.policy.force_task_mode:
        task_body = MediaTaskSubmitRequest(
            request_id=body.request_id,
            capability="image.generate",
            caller=body.caller,
            context=body.context,
            policy=body.policy,
            payload=body.payload.model_dump(),
        )
        task_result = submit_media_task(task_body)
        if task_result.result_state == "failed":
            return ImageGenerateResponse(
                request_id=body.request_id,
                result_state="failed",
                provider_id=task_result.provider_id,
                backend_id=task_result.backend_id,
                error=task_result.error,
            )
        return ImageGenerateResponse(
            request_id=body.request_id,
            result_state="accepted",
            task_id=task_result.task_id,
            provider_id=task_result.provider_id,
            backend_id=task_result.backend_id,
        )
    raw_result = await submit_image_generate(body)
    result = (
        raw_result
        if isinstance(raw_result, ImageGenerateResponse)
        else ImageGenerateResponse.model_validate(raw_result)
    )
    # 仅本地默认上游计入进程熔断；请求携带网关由 Bot 侧 circuit 负责
    used_request_gateway = any(item.from_request for item in resolve_image_backends(body))
    if result.result_state == "success":
        if not used_request_gateway:
            record_image_success(latency_ms=result.latency_ms)
        return result
    if result.error is not None and not used_request_gateway:
        err = (
            result.error
            if isinstance(result.error, RuntimeErrorBody)
            else RuntimeErrorBody.model_validate(result.error)
        )
        record_image_failure(failure_class=err.failure_class)
    return result


@router.get("/images/runtime", response_model=ImageRuntimeStatus)
async def get_image_runtime_status() -> ImageRuntimeStatus:
    return image_runtime_status()
