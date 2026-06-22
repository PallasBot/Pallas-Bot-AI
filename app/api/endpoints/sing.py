from fastapi import APIRouter, HTTPException

from app.schemas.sing import PlayRequest, RequestMusicRequest, SingRequest, SingResponse
from app.services.sing import download, play, sing

router = APIRouter()


@router.post("/sing/{request_id}", response_model=SingResponse)
async def sing_endpoint(request_id: str, request: SingRequest):
    task_id = await sing(
        request_id,
        request.speaker,
        request.song_id,
        request.key,
        request.chunk_index,
        request.sing_length,
    )
    return SingResponse(task_id=task_id, status="processing")


@router.post("/play/{request_id}", response_model=SingResponse)
async def play_endpoint(request_id: str, request: PlayRequest):
    task_id = await play(request_id, request.speaker)
    return SingResponse(task_id=task_id, status="processing")


@router.get("/play/{speaker}", response_model=SingResponse)
async def legacy_play_endpoint(speaker: str):
    _ = speaker
    raise HTTPException(status_code=410, detail="legacy play disabled; use POST /api/play/{request_id}")


@router.post("/request/{request_id}", response_model=SingResponse)
async def request_endpoint(request_id: str, request: RequestMusicRequest):
    task_id = await download(request_id, request.song_id)
    return SingResponse(task_id=task_id, status="processing")
