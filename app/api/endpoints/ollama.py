from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.logger import logger
from app.core.ollama_runtime import (
    get_ollama_model,
    reload_ollama_model_from_env,
    switch_ollama_model,
)
from app.schemas.ollama import (
    OllamaChatRequest,
    OllamaModelResponse,
    OllamaModelUpdateRequest,
    OllamaResponse,
)
from app.services.ollama import del_session, ollama_chat, unload

router = APIRouter()


@router.post("/ollama/chat/{request_id}", response_model=OllamaResponse)
async def ollama_chat_endpoint(request_id: str, request: OllamaChatRequest):
    if not settings.ollama_enable:
        raise HTTPException(status_code=503, detail="Ollama backend disabled")
    task_id = await ollama_chat(
        request_id,
        request.session,
        request.text,
        request.system_prompt,
        request.model,
    )
    return OllamaResponse(task_id=task_id, status="processing")


@router.delete("/ollama/del_session/{session}", response_model=OllamaResponse)
async def ollama_del_session_endpoint(session: str):
    logger.debug("Deleting ollama session: {}", session)
    await del_session(session)
    return OllamaResponse(task_id="", status="ok")


@router.get("/ollama/model", response_model=OllamaModelResponse)
async def ollama_get_model_endpoint():
    if not settings.ollama_enable:
        raise HTTPException(status_code=503, detail="Ollama backend disabled")
    return OllamaModelResponse(model=get_ollama_model())


@router.put("/ollama/model", response_model=OllamaModelResponse)
async def ollama_set_model_endpoint(request: OllamaModelUpdateRequest):
    if not settings.ollama_enable:
        raise HTTPException(status_code=503, detail="Ollama backend disabled")
    try:
        model = await switch_ollama_model(request.model, pull=request.pull)
    except Exception as e:
        logger.exception("ollama switch model failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    return OllamaModelResponse(model=model)


@router.post("/ollama/model/reload", response_model=OllamaModelResponse)
async def ollama_reload_model_endpoint():
    if not settings.ollama_enable:
        raise HTTPException(status_code=503, detail="Ollama backend disabled")
    model = reload_ollama_model_from_env()
    return OllamaModelResponse(model=model)


@router.post("/ollama/unload", response_model=OllamaResponse)
async def ollama_unload_endpoint():
    if not settings.ollama_enable:
        raise HTTPException(status_code=503, detail="Ollama backend disabled")
    status, body = await unload(None)
    if status == 200:
        return OllamaResponse(task_id="", status="ok")
    raise HTTPException(status_code=status, detail=body)
