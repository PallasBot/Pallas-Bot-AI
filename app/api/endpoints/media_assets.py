from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.media_assets import collect_asset_status, get_download_job, start_download_job

router = APIRouter(prefix="/media/assets", tags=["media-assets"])


@router.get("/status")
async def media_assets_status() -> dict:
    return collect_asset_status().as_dict()


@router.post("/download")
async def media_assets_download() -> dict:
    try:
        return start_download_job()
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/download/jobs/{job_id}")
async def media_assets_download_job(job_id: str) -> dict:
    job = get_download_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job
