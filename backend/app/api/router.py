from fastapi import APIRouter

from app.api import graph, repair, scan

api_router = APIRouter()

api_router.include_router(scan.router)
api_router.include_router(repair.router)
api_router.include_router(graph.router)