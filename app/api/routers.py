from fastapi import APIRouter

from app.api.endpoints import chat, sing

router = APIRouter()
router.include_router(sing.router)
router.include_router(chat.router)
