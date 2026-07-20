from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.media_assets import (
    collect_asset_status,
    delete_assets,
    get_download_job,
    start_download_job,
)

router = APIRouter(prefix="/media/assets", tags=["media-assets"])


class MediaAssetsDownloadBody(BaseModel):
    assets: list[str] | None = Field(
        default=None,
        description="要下载的资源包 id；缺省为全部缺失项",
    )


class MediaAssetsDeleteBody(BaseModel):
    assets: list[str] = Field(min_length=1, description="要删除的资源包 id")


@router.get("/status")
async def media_assets_status() -> dict:
    return collect_asset_status().as_dict()


@router.post("/download")
async def media_assets_download(body: MediaAssetsDownloadBody | None = None) -> dict:
    try:
        assets = body.assets if body is not None else None
        return start_download_job(assets=assets)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/delete")
async def media_assets_delete(body: MediaAssetsDeleteBody) -> dict:
    try:
        return delete_assets(assets=body.assets)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/download/jobs/{job_id}")
async def media_assets_download_job(job_id: str) -> dict:
    job = get_download_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job
