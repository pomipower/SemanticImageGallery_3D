"""Central API router — aggregates all sub-routers."""

from fastapi import APIRouter

from app.api.images import router as images_router
from app.api.folders import router as folders_router
from app.api.jobs import router as jobs_router

api_router = APIRouter(prefix="/api")

api_router.include_router(images_router)
api_router.include_router(folders_router)
api_router.include_router(jobs_router)
