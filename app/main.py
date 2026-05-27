import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import router as api_router
from app.core.config import settings
from app.core.ollama_runtime import ensure_ollama_ready, stop_ollama_if_started

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.ollama_enable:
        await ensure_ollama_ready()
    yield
    if settings.ollama_auto_start:
        stop_ollama_if_started()


app = FastAPI(lifespan=lifespan)
app.include_router(api_router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}
