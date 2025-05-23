from fastapi import APIRouter

from app.api.endpoints import sing

router = APIRouter()
router.include_router(sing.router)
