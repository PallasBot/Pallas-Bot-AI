from fastapi import APIRouter

from app.media.services.tts import tts
from app.schemas.tts import TTSRequest, TTSResponse

router = APIRouter()


@router.post("/tts/{request_id}", response_model=TTSResponse)
async def tts_endpoint(request_id: str, request: TTSRequest):
    task_id = await tts(request_id, request.text)
    return TTSResponse(task_id=task_id, status="processing")
