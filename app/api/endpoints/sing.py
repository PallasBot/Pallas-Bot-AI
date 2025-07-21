from fastapi import APIRouter

from app.schemas.sing import SingRequest, SingResponse
from app.services.sing import play, sing

router = APIRouter()


@router.post("/sing/{request_id}", response_model=SingResponse)
async def sing_endpoint(request_id: str, request: SingRequest):
    task_id = await sing(request_id, request.speaker, request.song_id, request.key, request.chunk_index)
    return SingResponse(task_id=task_id, status="processing")


@router.get("/play/{speaker}", response_model=SingResponse)
async def play_endpoint(speaker: str):
    task_id = await play(speaker)
    return SingResponse(task_id=task_id, status="processing")
