from fastapi import FastAPI

from app.api.routers import router as api_router

app = FastAPI()
app.include_router(api_router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok"}
