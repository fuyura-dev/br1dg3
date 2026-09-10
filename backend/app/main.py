from fastapi import FastAPI

from app.config import settings
from app.api.router import api_router

app = FastAPI()

app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "status": "online"
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}