"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import init_db
from app.pipeline.worker import start_worker, stop_worker

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_worker_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    global _worker_task

    # --- Startup ---
    settings.ensure_dirs()
    await init_db()
    _worker_task = await start_worker()
    logger.info("SemanticImageGallery backend ready")
    logger.info("Data directory: %s", settings.data_dir)

    yield

    # --- Shutdown ---
    await stop_worker()
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except Exception:
            pass
    logger.info("Backend shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow Vue dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}
