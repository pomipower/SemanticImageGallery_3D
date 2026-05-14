"""Job queue endpoints — monitoring and SSE stream."""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_db
from app.models.models import Job
from app.schemas.schemas import JobList, JobRead, StatsRead
from app.models.models import Image, ImageFolder

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


@router.get("", response_model=JobList)
async def list_jobs(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List recent jobs, optionally filtered by status."""
    query = select(Job).order_by(Job.created_at.desc()).limit(limit)
    count_query = select(func.count(Job.id))

    if status:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)

    result = await db.execute(query)
    jobs = result.scalars().all()

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    return JobList(
        items=[JobRead.model_validate(j) for j in jobs],
        total=total,
    )


@router.get("/stats", response_model=StatsRead)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Overall system statistics."""

    async def _count(model, **filters):
        q = select(func.count(model.id))
        for k, v in filters.items():
            q = q.where(getattr(model, k) == v)
        r = await db.execute(q)
        return r.scalar() or 0

    return StatsRead(
        total_images=await _count(Image),
        indexed_images=await _count(Image, status="indexed"),
        pending_images=await _count(Image, status="pending"),
        error_images=await _count(Image, status="error"),
        total_folders=await _count(ImageFolder),
        queued_jobs=await _count(Job, status="queued"),
        running_jobs=await _count(Job, status="running"),
    )


@router.get("/stream")
async def job_stream():
    """SSE endpoint — pushes job stats every 2 seconds."""

    async def _generate():
        while True:
            try:
                async with async_session_factory() as db:
                    result = await db.execute(
                        select(
                            Job.status,
                            func.count(Job.id),
                        ).group_by(Job.status)
                    )
                    counts = {row[0]: row[1] for row in result.all()}

                data = json.dumps(counts)
                yield f"data: {data}\n\n"
            except Exception as e:
                logger.error("SSE error: %s", e)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

            await asyncio.sleep(2)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/embed-all")
async def embed_all_images(db: AsyncSession = Depends(get_db)):
    """Create embed jobs for all images missing embeddings."""
    result = await db.execute(
        select(Image).where(
            Image.status != "deleted",
            Image.embedding_status == "pending",
        )
    )
    images = result.scalars().all()
    count = 0
    for img in images:
        db.add(Job(type="embed", image_id=img.id, priority=2))
        count += 1
    await db.commit()
    return {"jobs_created": count}


@router.post("/process-all")
async def process_all_metadata(db: AsyncSession = Depends(get_db)):
    """Create OCR + caption jobs for all indexed images missing metadata."""
    from app.models.models import OcrResult, Caption

    # Find images that are indexed but have no OCR or caption
    result = await db.execute(
        select(Image).where(Image.status == "indexed")
    )
    images = result.scalars().all()

    ocr_count = 0
    caption_count = 0
    for img in images:
        # Check if OCR already done
        ocr_exists = await db.execute(
            select(OcrResult.id).where(OcrResult.image_id == img.id).limit(1)
        )
        if ocr_exists.scalar_one_or_none() is None:
            # Check no queued/running OCR job exists
            existing_job = await db.execute(
                select(Job).where(
                    Job.image_id == img.id, Job.type == "ocr",
                    Job.status.in_(["queued", "running"]),
                )
            )
            if existing_job.scalar_one_or_none() is None:
                db.add(Job(type="ocr", image_id=img.id, priority=3))
                ocr_count += 1

        # Check if caption already done
        cap_exists = await db.execute(
            select(Caption.id).where(Caption.image_id == img.id).limit(1)
        )
        if cap_exists.scalar_one_or_none() is None:
            existing_job = await db.execute(
                select(Job).where(
                    Job.image_id == img.id, Job.type == "caption",
                    Job.status.in_(["queued", "running"]),
                )
            )
            if existing_job.scalar_one_or_none() is None:
                db.add(Job(type="caption", image_id=img.id, priority=4))
                caption_count += 1

    await db.commit()
    return {"ocr_jobs": ocr_count, "caption_jobs": caption_count}
