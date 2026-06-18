from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.logger import logger
from app.schemas.persona_affect import AffectRefineRequest, AffectRefineResponse
from app.services.persona_affect import refine_group_affect

router = APIRouter()


@router.post("/persona/affect-refine", response_model=AffectRefineResponse)
async def persona_affect_refine_endpoint(request: AffectRefineRequest) -> AffectRefineResponse:
    if not settings.persona_affect_refine_enabled:
        raise HTTPException(status_code=503, detail="persona affect refine disabled")
    if not settings.llm_chat_enabled and not settings.persona_affect_refine_allow_heuristic:
        raise HTTPException(status_code=503, detail="llm backend disabled")

    logger.info(
        "persona affect refine: group={} samples={} hints={}",
        request.group_id,
        len(request.message_samples),
        len(request.hints),
    )
    return await refine_group_affect(request)
