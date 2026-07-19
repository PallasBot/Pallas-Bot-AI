from fastapi import APIRouter

from app.services.llm_task_metrics import llm_task_metrics_snapshot
from app.services.llm_token_metrics import llm_token_metrics_snapshot

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/stats")
def llm_task_stats_endpoint():
    return {
        **llm_task_metrics_snapshot(),
        "tokens": llm_token_metrics_snapshot(),
    }
