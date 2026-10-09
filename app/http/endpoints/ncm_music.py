from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.http.deps.api_auth import require_configured_api_bearer_token
from app.media.services.ncm_loader import get_song_detail, get_song_id
from app.media.services.ncm_login import ncm_login_manager

router = APIRouter(
    prefix="/ncm",
    tags=["网易云音乐"],
    dependencies=[Depends(require_configured_api_bearer_token)],
)


@router.get("/search")
async def search_song(q: str = Query(min_length=1, max_length=200)) -> dict[str, int | str | None]:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="搜索内容不能为空")
    return {
        "song_id": await get_song_id(
            query,
            exclude_vip=ncm_login_manager.session is None,
        )
    }


@router.get("/songs/{song_id}")
async def song_detail(song_id: int = Path(ge=1)) -> dict[str, str | list[str]]:
    detail = await get_song_detail(song_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="歌曲不存在")
    return detail
