import logging

from fastapi import FastAPI

from app.api.routers import router as api_router

# 将 uvicorn access log 降为 WARNING，避免每次请求都刷日志
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

app = FastAPI()
app.include_router(api_router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}
