from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.router import api_router

app = FastAPI(title=settings.PROJECT_NAME)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Allows all origins, including Chrome extensions
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allows all request headers
)

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
