from fastapi import APIRouter, Body, HTTPException

from app.core.config import settings
from app.core.logger import logger
from app.schemas.llm_api import LlmTaskResponse
from app.schemas.llm_chat import LlmChatCompletionResponse
from app.schemas.llm_replay import LlmReplayRequest, LlmReplayResponse
from app.services.llm_chat import delete_llm_chat_session, submit_llm_chat_completion
from app.services.llm_chat_request import parse_llm_chat_completion_request
from app.services.llm_replay import run_llm_replay

router = APIRouter()


@router.post("/v1/chat/completions/{request_id}", response_model=LlmChatCompletionResponse)
async def llm_chat_completions_endpoint(request_id: str, body: dict = Body(...)):
    if not settings.llm_chat_enabled:
        raise HTTPException(status_code=503, detail="unified llm chat disabled")
    try:
        request = parse_llm_chat_completion_request(body)
        task_id = await submit_llm_chat_completion(request_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("llm chat submit failed: request_id={}", request_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LlmChatCompletionResponse(task_id=task_id, status="processing")


@router.post("/v1/chat/replay", response_model=LlmReplayResponse)
async def llm_chat_replay_endpoint(request: LlmReplayRequest):
    if not settings.llm_chat_enabled:
        raise HTTPException(status_code=503, detail="unified llm chat disabled")
    try:
        return await run_llm_replay(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("llm replay failed: request_id={}", request.request_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/v1/chat/completions/session/{session_id}", response_model=LlmTaskResponse)
async def llm_chat_delete_session_endpoint(session_id: str):
    logger.info("llm chat del_session: session={}", session_id)
    await delete_llm_chat_session(session_id)
    return LlmTaskResponse(task_id="", status="ok")
