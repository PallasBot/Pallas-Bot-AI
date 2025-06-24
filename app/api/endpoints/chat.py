from fastapi import APIRouter

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import chat
from app.tasks.chat.chat_tasks import del_session

router = APIRouter()


@router.post("/chat/{request_id}", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, request_id: str):
    task_id = await chat(request_id, request.session, request.text, request.token_count, request.tts)
    return ChatResponse(task_id=task_id, status="processing")


@router.delete("/del_session", response_model=ChatResponse)
async def del_session_endpoint(session: str = ""):
    await del_session(session)
    return ChatResponse(task_id="", status="processing")
