from fastapi import APIRouter

from app.schemas.sing import SingRequest, SingResponse
from app.services.sing import play, sing

router = APIRouter()


@router.post("/sing", response_model=SingResponse)
async def sing_endpoint(request: SingRequest):
    task_id = await sing(request.speaker, request.song_id, request.key, request.chunk_index)
    return SingResponse(task_id=task_id, status="processing")


@router.get("/play", response_model=SingResponse)
async def play_endpoint(speaker: str = ""):
    await play(speaker)
    return SingResponse(task_id="", status="processing")
