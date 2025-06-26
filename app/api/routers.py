from fastapi import APIRouter

from app.api.endpoints import chat, sing, tts

router = APIRouter()
router.include_router(sing.router)
router.include_router(chat.router)
router.include_router(tts.router)
