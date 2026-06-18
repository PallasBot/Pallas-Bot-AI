from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.llm_backend_runtime import (
    get_llm_model,
    get_llm_num_gpu,
    mark_llm_gpu_config_dirty,
    reload_llm_runtime_from_env,
    switch_llm_model,
    switch_llm_num_gpu,
)
from app.core.logger import logger
from app.schemas.llm_api import (
    LlmLegacyChatRequest,
    LlmModelResponse,
    LlmModelUpdateRequest,
    LlmNumGpuUpdateRequest,
    LlmTaskResponse,
)
from app.schemas.llm_chat import LlmChatCompletionRequest, LlmChatMessage
from app.services.llm_chat import submit_llm_chat_completion
from app.services.llm_queue import delete_chat_session, unload_local_model

router = APIRouter()
legacy_router = APIRouter()


def _llm_disabled() -> HTTPException:
    return HTTPException(status_code=503, detail="llm chat backend disabled")


async def _legacy_chat(request_id: str, request: LlmLegacyChatRequest) -> LlmTaskResponse:
    if not settings.llm_chat_enabled:
        raise _llm_disabled()
    logger.info(
        "llm legacy chat api: request_id={} session={} text_len={} task={}",
        request_id,
        request.session,
        len(request.text or ""),
        (request.metadata or {}).get("task"),
    )
    try:
        task_id = await submit_llm_chat_completion(
            request_id,
            LlmChatCompletionRequest(
                session_id=request.session,
                system=request.system_prompt,
                messages=[LlmChatMessage(role="user", content=request.text)],
                model=request.model,
                metadata=request.metadata,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return LlmTaskResponse(task_id=task_id, status="processing")


async def _delete_session(session: str) -> LlmTaskResponse:
    logger.info("llm del_session api: session={}", session)
    await delete_chat_session(session)
    return LlmTaskResponse(task_id="", status="ok")


async def _get_model() -> LlmModelResponse:
    if not settings.llm_chat_enabled:
        raise _llm_disabled()
    return LlmModelResponse(model=get_llm_model(), num_gpu=get_llm_num_gpu())


async def _set_model(request: LlmModelUpdateRequest) -> LlmModelResponse:
    if not settings.llm_chat_enabled:
        raise _llm_disabled()
    logger.info("llm set model api: model={} pull={}", request.model, request.pull)
    try:
        model = await switch_llm_model(request.model, pull=request.pull)
    except Exception as exc:
        logger.exception("llm switch model failed: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LlmModelResponse(model=model, num_gpu=get_llm_num_gpu())


async def _set_num_gpu(request: LlmNumGpuUpdateRequest) -> LlmModelResponse:
    if not settings.llm_chat_enabled:
        raise _llm_disabled()
    logger.info("llm set num_gpu api: num_gpu={}", request.num_gpu)
    try:
        num_gpu = await switch_llm_num_gpu(request.num_gpu)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("llm switch num_gpu failed: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LlmModelResponse(model=get_llm_model(), num_gpu=num_gpu)


async def _reload_model() -> LlmModelResponse:
    if not settings.llm_chat_enabled:
        raise _llm_disabled()
    model, num_gpu = reload_llm_runtime_from_env()
    mark_llm_gpu_config_dirty()
    try:
        status, body = await unload_local_model(None)
        if status != 200:
            logger.warning("llm reload: unload returned {} {}", status, body)
    except Exception as exc:
        logger.warning("llm reload: unload failed: {}", exc)
    return LlmModelResponse(model=model, num_gpu=num_gpu)


async def _unload() -> LlmTaskResponse:
    if not settings.llm_chat_enabled:
        raise _llm_disabled()
    logger.info("llm unload api")
    status, body = await unload_local_model(None)
    if status == 200:
        logger.info("llm unload ok")
        return LlmTaskResponse(task_id="", status="ok")
    logger.warning("llm unload failed: status={} body={}", status, body)
    raise HTTPException(status_code=status, detail=body)


router.post("/llm/chat/{request_id}", response_model=LlmTaskResponse)(_legacy_chat)
router.delete("/llm/del_session/{session}", response_model=LlmTaskResponse)(_delete_session)
router.get("/llm/model", response_model=LlmModelResponse)(_get_model)
router.put("/llm/model", response_model=LlmModelResponse)(_set_model)
router.post("/llm/model/num-gpu", response_model=LlmModelResponse)(_set_num_gpu)
router.post("/llm/model/reload", response_model=LlmModelResponse)(_reload_model)
router.post("/llm/unload", response_model=LlmTaskResponse)(_unload)

legacy_router.post("/ollama/chat/{request_id}", response_model=LlmTaskResponse)(_legacy_chat)
legacy_router.delete("/ollama/del_session/{session}", response_model=LlmTaskResponse)(_delete_session)
legacy_router.get("/ollama/model", response_model=LlmModelResponse)(_get_model)
legacy_router.put("/ollama/model", response_model=LlmModelResponse)(_set_model)
legacy_router.post("/ollama/model/num-gpu", response_model=LlmModelResponse)(_set_num_gpu)
legacy_router.post("/ollama/model/reload", response_model=LlmModelResponse)(_reload_model)
legacy_router.post("/ollama/unload", response_model=LlmTaskResponse)(_unload)
