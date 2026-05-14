"""Image endpoints — list, detail, thumbnail serving."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.models import Image
from app.schemas.schemas import ImageList, ImageRead

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)


@router.get("", response_model=ImageList)
async def list_images(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Paginated image list, optionally filtered by status."""
    query = select(Image).where(Image.status != "deleted")
    count_query = select(func.count(Image.id)).where(Image.status != "deleted")

    if status:
        query = query.where(Image.status == status)
        count_query = count_query.where(Image.status == status)

    query = query.order_by(Image.indexed_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    images = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return ImageList(
        items=[ImageRead.model_validate(img) for img in images],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{image_id}", response_model=ImageRead)
async def get_image(image_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single image by ID."""
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return ImageRead.model_validate(image)


@router.get("/{image_id}/thumbnail")
async def get_thumbnail(image_id: int, db: AsyncSession = Depends(get_db)):
    """Serve the thumbnail file for an image."""
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if not image or not image.thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    thumb = Path(image.thumbnail_path)
    if not thumb.exists():
        raise HTTPException(status_code=404, detail="Thumbnail file missing")

    return FileResponse(
        thumb,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/{image_id}/full")
async def get_full_image(image_id: int, db: AsyncSession = Depends(get_db)):
    """Serve the original full-resolution image."""
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    path = Path(image.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file missing")

    media_type = "image/jpeg" if image.format == "jpg" else f"image/{image.format or 'jpeg'}"
    return FileResponse(path, media_type=media_type)


@router.get("/{image_id}/metadata")
async def get_image_metadata(image_id: int, db: AsyncSession = Depends(get_db)):
    """Get all metadata for an image: captions, tags, OCR."""
    from app.models.models import Caption, Tag, OcrResult

    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Captions
    cap_result = await db.execute(
        select(Caption).where(Caption.image_id == image_id).order_by(Caption.created_at.desc())
    )
    captions = [{"caption": c.caption, "model": c.model} for c in cap_result.scalars().all()]

    # Tags
    tag_result = await db.execute(
        select(Tag).where(Tag.image_id == image_id)
    )
    tags = [{"tag": t.tag, "source": t.source, "confidence": t.confidence} for t in tag_result.scalars().all()]

    # OCR
    ocr_result = await db.execute(
        select(OcrResult).where(OcrResult.image_id == image_id).order_by(OcrResult.created_at.desc())
    )
    ocr_items = [{"text": o.text, "engine": o.engine, "confidence": o.confidence} for o in ocr_result.scalars().all()]

    return {
        "image_id": image_id,
        "captions": captions,
        "tags": tags,
        "ocr": ocr_items,
    }
