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
from app.models.models import Image, Job
from app.pipeline.thumbnail import (
    extract_exif,
    generate_thumbnail,
    get_image_dimensions,
    get_image_format,
)

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound work (thumbnail gen, hashing)
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
        if job.type == "thumbnail":
            await _handle_thumbnail(db, job)
        elif job.type == "embed":
            await _handle_embed(db, job)
        else:
            logger.warning("Unknown job type: %s (job %d) — skipping", job.type, job.id)
            job.status = "queued"  # put back for future milestone workers
            await db.commit()
            return

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


async def _handle_thumbnail(db: AsyncSession, job: Job) -> None:
    """Generate thumbnail, extract EXIF, update image dimensions."""
    result = await db.execute(select(Image).where(Image.id == job.image_id))
    image = result.scalar_one_or_none()
    if image is None:
        raise ValueError(f"Image {job.image_id} not found")

    image_path = Path(image.file_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image file missing: {image_path}")

    loop = asyncio.get_running_loop()

    # Run CPU-bound work in thread pool
    thumb_path, dimensions, exif_json, fmt = await loop.run_in_executor(
        _executor,
        _thumbnail_work,
        image_path,
        image.file_hash,
    )

    # Update image record
    image.thumbnail_path = str(thumb_path)
    image.width = dimensions[0]
    image.height = dimensions[1]
    image.exif_json = exif_json
    image.format = fmt
    image.status = "indexed"

    await db.commit()

    # Populate FTS5 with filename for keyword search
    try:
        filename = image_path.stem
        await db.execute(
            text(
                "INSERT OR REPLACE INTO images_fts(rowid, filename, caption, tags, ocr_text) "
                "VALUES (:id, :fn, '', '', '')"
            ),
            {"id": image.id, "fn": filename},
        )
        await db.commit()
    except Exception:
        pass  # FTS5 table may not exist yet during migration


def _thumbnail_work(image_path: Path, file_hash: str) -> tuple[Path, tuple[int, int], str | None, str]:
    """Synchronous thumbnail + metadata extraction (runs in thread pool)."""
    thumb = generate_thumbnail(image_path, file_hash)
    dims = get_image_dimensions(image_path)
    exif = extract_exif(image_path)
    fmt = get_image_format(image_path)
    return thumb, dims, exif, fmt


async def _handle_embed(db: AsyncSession, job: Job) -> None:
    """Generate CLIP embedding and store in LanceDB."""
    result = await db.execute(select(Image).where(Image.id == job.image_id))
    image = result.scalar_one_or_none()
    if image is None:
        raise ValueError(f"Image {job.image_id} not found")

    image_path = Path(image.file_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image file missing: {image_path}")

    loop = asyncio.get_running_loop()

    # Run CLIP encoding in thread pool (CPU-bound)
    vector = await loop.run_in_executor(_executor, _embed_work, image_path)

    # Store in LanceDB
    from app.core.vector_store import get_vector_store
    store = get_vector_store()
    store.upsert_image_embedding(image.id, vector, image.file_path)

    # Update embedding status
    image.embedding_status = "done"
    await db.commit()


def _embed_work(image_path: Path):
    """Synchronous CLIP encoding (runs in thread pool)."""
    from app.ml.clip import get_clip_encoder
    encoder = get_clip_encoder()
    return encoder.encode_image(image_path)
