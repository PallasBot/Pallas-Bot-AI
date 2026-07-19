from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps.api_auth import require_api_bearer_token
from app.services.service_logs import resolve_service_log_path, tail_log_lines

router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(require_api_bearer_token)])


@router.get("/logs")
def service_logs_endpoint(
    kind: Literal["uvicorn", "celery", "celery-media"] = Query(default="uvicorn"),
    n: int = Query(default=200, ge=1, le=2000),
) -> dict[str, object]:
    path = resolve_service_log_path(kind)
    path_s = str(path) if path is not None else ""
    if path is None or not path.is_file():
        return {
            "kind": kind,
            "path": path_s,
            "lines": [],
            "error": "日志文件不存在",
            "source": "ai",
        }
    try:
        lines = tail_log_lines(path, n)
    except OSError as e:
        return {
            "kind": kind,
            "path": path_s,
            "lines": [],
            "error": str(e),
            "source": "ai",
        }
    return {
        "kind": kind,
        "path": path_s,
        "lines": lines,
        "error": None,
        "source": "ai",
    }
