from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.media_task_runtime import (
    get_media_task,
    media_task_runtime_status,
    submit_media_task,
)
from app.schemas.media_task_api import (
    MediaTaskRuntimeStatus,
    MediaTaskStatus,
    MediaTaskSubmitRequest,
    MediaTaskSubmitResponse,
)

router = APIRouter()


@router.post("/media/tasks", response_model=MediaTaskSubmitResponse)
async def post_media_task(body: MediaTaskSubmitRequest) -> MediaTaskSubmitResponse:
    return submit_media_task(body)


@router.get("/media/tasks/runtime", response_model=MediaTaskRuntimeStatus)
async def get_media_task_runtime() -> MediaTaskRuntimeStatus:
    return media_task_runtime_status()


@router.get("/media/tasks/{task_id}", response_model=MediaTaskStatus)
async def get_media_task_status(task_id: str) -> MediaTaskStatus:
    status = get_media_task(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="task not found")
    return status
