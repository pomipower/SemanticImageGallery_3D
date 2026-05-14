"""Background worker — polls the job queue and dispatches work.

Spawned as an asyncio.Task at FastAPI startup. Heavy CPU work is
offloaded to a ThreadPoolExecutor to avoid blocking the event loop.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.models import Image, Job, Caption, Tag, OcrResult
from app.pipeline.thumbnail import (
    extract_exif,
    generate_thumbnail,
    get_image_dimensions,
    get_image_format,
)

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound work (thumbnail gen, hashing, OCR)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="worker")

# Flag to gracefully stop the worker loop
_shutdown_event = asyncio.Event()


async def start_worker() -> asyncio.Task:
    """Create and return the background worker task."""
    _shutdown_event.clear()
    task = asyncio.create_task(_worker_loop(), name="job-worker")
    logger.info("Background worker started")
    return task


async def stop_worker() -> None:
    """Signal the worker to stop."""
    _shutdown_event.set()
    logger.info("Background worker stop requested")


async def _worker_loop() -> None:
    """Main loop: poll for queued jobs and process them."""
    while not _shutdown_event.is_set():
        try:
            async with async_session_factory() as db:
                job = await _claim_next_job(db)
                if job is None:
                    # No work — wait before polling again
                    try:
                        await asyncio.wait_for(
                            _shutdown_event.wait(),
                            timeout=settings.worker_poll_interval,
                        )
                    except asyncio.TimeoutError:
                        pass
                    continue

                await _process_job(db, job)
        except Exception:
            logger.exception("Worker loop error")
            await asyncio.sleep(1)  # back off on unexpected errors


async def _claim_next_job(db: AsyncSession) -> Job | None:
    """Atomically claim the highest-priority queued job."""
    result = await db.execute(
        select(Job)
        .where(Job.status == "queued")
        .order_by(Job.priority.asc(), Job.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await db.commit()
    return job


async def _process_job(db: AsyncSession, job: Job) -> None:
    """Dispatch a job to the appropriate handler."""
    try:
        handlers = {
            "thumbnail": _handle_thumbnail,
            "embed": _handle_embed,
            "ocr": _handle_ocr,
            "caption": _handle_caption,
        }
        handler = handlers.get(job.type)
        if handler is None:
            logger.warning("Unknown job type: %s (job %d) — skipping", job.type, job.id)
            job.status = "queued"
            await db.commit()
            return

        await handler(db, job)

        job.status = "done"
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("Job %d (%s) completed for image %s", job.id, job.type, job.image_id)

    except Exception as e:
        logger.exception("Job %d failed: %s", job.id, e)
        job.retries += 1
        if job.retries >= settings.max_retries:
            job.status = "failed"
            job.error = str(e)[:500]
        else:
            job.status = "queued"  # retry
            job.error = str(e)[:500]
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()


# ── THUMBNAIL ────────────────────────────────────────────────────────

async def _handle_thumbnail(db: AsyncSession, job: Job) -> None:
    """Generate thumbnail, extract EXIF, update image dimensions."""
    image = await _load_image(db, job.image_id)
    image_path = Path(image.file_path)

    loop = asyncio.get_running_loop()
    thumb_path, dimensions, exif_json, fmt = await loop.run_in_executor(
        _executor, _thumbnail_work, image_path, image.file_hash,
    )

    image.thumbnail_path = str(thumb_path)
    image.width = dimensions[0]
    image.height = dimensions[1]
    image.exif_json = exif_json
    image.format = fmt
    image.status = "indexed"
    await db.commit()

    # Populate FTS5 with filename for keyword search
    await _update_fts5(db, image)


def _thumbnail_work(image_path: Path, file_hash: str) -> tuple[Path, tuple[int, int], str | None, str]:
    """Synchronous thumbnail + metadata extraction (runs in thread pool)."""
    thumb = generate_thumbnail(image_path, file_hash)
    dims = get_image_dimensions(image_path)
    exif = extract_exif(image_path)
    fmt = get_image_format(image_path)
    return thumb, dims, exif, fmt


# ── EMBED ────────────────────────────────────────────────────────────

async def _handle_embed(db: AsyncSession, job: Job) -> None:
    """Generate CLIP embedding and store in LanceDB."""
    image = await _load_image(db, job.image_id)
    image_path = Path(image.file_path)

    loop = asyncio.get_running_loop()
    vector = await loop.run_in_executor(_executor, _embed_work, image_path)

    from app.core.vector_store import get_vector_store
    store = get_vector_store()
    store.upsert_image_embedding(image.id, vector, image.file_path)

    image.embedding_status = "done"
    await db.commit()


def _embed_work(image_path: Path):
    """Synchronous CLIP encoding (runs in thread pool)."""
    from app.ml.clip import get_clip_encoder
    encoder = get_clip_encoder()
    return encoder.encode_image(image_path)


# ── OCR ──────────────────────────────────────────────────────────────

async def _handle_ocr(db: AsyncSession, job: Job) -> None:
    """Extract text from image using EasyOCR."""
    image = await _load_image(db, job.image_id)
    image_path = Path(image.file_path)

    loop = asyncio.get_running_loop()
    ocr_text, confidence = await loop.run_in_executor(
        _executor, _ocr_work, image_path,
    )

    if ocr_text:
        # Remove old OCR results for this image
        await db.execute(
            select(OcrResult).where(OcrResult.image_id == image.id)
        )
        from sqlalchemy import delete
        await db.execute(delete(OcrResult).where(OcrResult.image_id == image.id))

        db.add(OcrResult(
            image_id=image.id,
            text=ocr_text,
            engine="easyocr",
            confidence=confidence,
        ))
        await db.commit()

        # Update FTS5
        await _update_fts5(db, image)


def _ocr_work(image_path: Path) -> tuple[str, float]:
    """Synchronous OCR (runs in thread pool)."""
    from app.ml.ocr import get_ocr_engine
    engine = get_ocr_engine()
    return engine.extract_text(image_path)


# ── CAPTION ──────────────────────────────────────────────────────────

async def _handle_caption(db: AsyncSession, job: Job) -> None:
    """Generate caption + tags using Ollama moondream."""
    image = await _load_image(db, job.image_id)
    image_path = Path(image.file_path)

    from app.ml.captioner import generate_caption, generate_tags, check_ollama_available

    # Check if Ollama is running
    if not await check_ollama_available():
        logger.warning("Ollama not available — skipping caption for image %d", image.id)
        # Don't fail the job, just skip
        return

    # Generate caption (async HTTP, no thread pool needed)
    caption_text = await generate_caption(image_path)
    if caption_text:
        from sqlalchemy import delete
        await db.execute(delete(Caption).where(Caption.image_id == image.id))
        db.add(Caption(
            image_id=image.id,
            caption=caption_text,
            model="moondream",
        ))

    # Generate tags
    tags = await generate_tags(image_path)
    if tags:
        from sqlalchemy import delete
        await db.execute(delete(Tag).where(
            Tag.image_id == image.id,
            Tag.source == "llm",
        ))
        for tag_str in tags:
            db.add(Tag(
                image_id=image.id,
                tag=tag_str,
                source="llm",
            ))

    await db.commit()

    # Update FTS5
    await _update_fts5(db, image)


# ── HELPERS ──────────────────────────────────────────────────────────

async def _load_image(db: AsyncSession, image_id: int) -> Image:
    """Load image by ID, raise if not found or file missing."""
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if image is None:
        raise ValueError(f"Image {image_id} not found")
    if not Path(image.file_path).exists():
        raise FileNotFoundError(f"Image file missing: {image.file_path}")
    return image


async def _update_fts5(db: AsyncSession, image: Image) -> None:
    """Update FTS5 index with latest metadata for an image."""
    try:
        # Gather current metadata
        filename = Path(image.file_path).stem

        # Get caption
        cap_result = await db.execute(
            select(Caption).where(Caption.image_id == image.id).limit(1)
        )
        caption_obj = cap_result.scalar_one_or_none()
        caption_text = caption_obj.caption if caption_obj else ""

        # Get tags
        tag_result = await db.execute(
            select(Tag).where(Tag.image_id == image.id)
        )
        tags = [t.tag for t in tag_result.scalars().all()]
        tags_text = " ".join(tags)

        # Get OCR
        ocr_result = await db.execute(
            select(OcrResult).where(OcrResult.image_id == image.id).limit(1)
        )
        ocr_obj = ocr_result.scalar_one_or_none()
        ocr_text = ocr_obj.text if ocr_obj else ""

        # Upsert FTS5 (delete + insert for contentless table)
        await db.execute(
            text("INSERT INTO images_fts(images_fts, rowid, filename, caption, tags, ocr_text) VALUES('delete', :id, :fn, :cap, :tags, :ocr)"),
            {"id": image.id, "fn": filename, "cap": "", "tags": "", "ocr": ""},
        )
        await db.execute(
            text("INSERT INTO images_fts(rowid, filename, caption, tags, ocr_text) VALUES (:id, :fn, :cap, :tags, :ocr)"),
            {"id": image.id, "fn": filename, "cap": caption_text, "tags": tags_text, "ocr": ocr_text},
        )
        await db.commit()
    except Exception as e:
        logger.debug("FTS5 update failed for image %d: %s", image.id, e)
