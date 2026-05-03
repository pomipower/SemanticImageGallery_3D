"""Folder management + scan trigger endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import ImageFolder
from app.pipeline.indexer import run_scan
from app.schemas.schemas import FolderCreate, FolderRead, ScanRequest, ScanResponse

router = APIRouter(prefix="/folders", tags=["folders"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[FolderRead])
async def list_folders(db: AsyncSession = Depends(get_db)):
    """List all registered image folders."""
    result = await db.execute(select(ImageFolder).order_by(ImageFolder.id))
    return [FolderRead.model_validate(f) for f in result.scalars().all()]


@router.post("", response_model=FolderRead, status_code=201)
async def add_folder(body: FolderCreate, db: AsyncSession = Depends(get_db)):
    """Register a new folder to watch."""
    # Normalize path
    folder_path = str(Path(body.path).resolve())

    # Check folder exists on disk
    if not Path(folder_path).is_dir():
        raise HTTPException(status_code=400, detail=f"Directory not found: {folder_path}")

    # Check for duplicate
    result = await db.execute(select(ImageFolder).where(ImageFolder.path == folder_path))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Folder already registered")

    folder = ImageFolder(
        path=folder_path,
        recursive=body.recursive,
        face_detection_enabled=body.face_detection_enabled,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    logger.info("Registered folder: %s", folder_path)
    return FolderRead.model_validate(folder)


@router.delete("/{folder_id}", status_code=204)
async def remove_folder(folder_id: int, db: AsyncSession = Depends(get_db)):
    """Unregister a folder (does NOT delete images from DB)."""
    result = await db.execute(select(ImageFolder).where(ImageFolder.id == folder_id))
    folder = result.scalar_one_or_none()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    await db.delete(folder)
    await db.commit()


@router.post("/scan", response_model=ScanResponse)
async def trigger_scan(body: ScanRequest, db: AsyncSession = Depends(get_db)):
    """Trigger a manual scan of registered folders."""
    stats = await run_scan(db, folder_id=body.folder_id)
    return ScanResponse(
        new_images=stats["new"],
        modified_images=stats["modified"],
        deleted_images=stats["deleted"],
        jobs_created=stats["jobs"],
    )
