"""Indexer — change detection + job creation.

Compares scanned files against the DB to find new / modified / deleted images,
then inserts appropriate job records.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Image, ImageFolder, Job
from app.pipeline.scanner import ScannedFile, compute_file_hash, scan_folder

logger = logging.getLogger(__name__)


async def run_scan(
    db: AsyncSession,
    folder_id: int | None = None,
) -> dict[str, int]:
    """
    Scan registered folders and create jobs for new/modified images.

    Returns {"new": N, "modified": M, "deleted": D, "jobs": J}.
    """
    # 1. Determine which folders to scan
    if folder_id:
        result = await db.execute(select(ImageFolder).where(ImageFolder.id == folder_id))
        folders = list(result.scalars().all())
    else:
        result = await db.execute(select(ImageFolder))
        folders = list(result.scalars().all())

    if not folders:
        return {"new": 0, "modified": 0, "deleted": 0, "jobs": 0}

    stats = {"new": 0, "modified": 0, "deleted": 0, "jobs": 0}

    for folder in folders:
        folder_path = Path(folder.path)
        if not folder_path.is_dir():
            logger.warning("Folder not found, skipping: %s", folder.path)
            continue

        scanned = scan_folder(folder_path, recursive=folder.recursive)
        scanned_by_path: dict[str, ScannedFile] = {str(sf.path): sf for sf in scanned}

        # 2. Get existing images from this folder
        prefix = str(folder_path)
        result = await db.execute(
            select(Image).where(Image.file_path.startswith(prefix))
        )
        existing_images = {img.file_path: img for img in result.scalars().all()}

        # 3. Find new and modified files
        for path_str, sf in scanned_by_path.items():
            if path_str not in existing_images:
                # New file — compute hash, insert image + job
                file_hash = compute_file_hash(sf.path)
                new_image = Image(
                    file_path=path_str,
                    file_hash=file_hash,
                    file_size=sf.size,
                    modified_at=datetime.fromtimestamp(sf.mtime, tz=timezone.utc),
                    status="pending",
                )
                db.add(new_image)
                await db.flush()  # get the ID

                db.add(Job(type="thumbnail", image_id=new_image.id, priority=1))
                db.add(Job(type="embed", image_id=new_image.id, priority=2))
                stats["new"] += 1
                stats["jobs"] += 2

            else:
                # Existing file — check mtime + size for fast change detection
                img = existing_images[path_str]
                stored_mtime = img.modified_at.timestamp() if img.modified_at else 0
                if abs(sf.mtime - stored_mtime) > 1 or sf.size != img.file_size:
                    # Potentially modified — compute hash to confirm
                    file_hash = compute_file_hash(sf.path)
                    if file_hash != img.file_hash:
                        img.file_hash = file_hash
                        img.file_size = sf.size
                        img.modified_at = datetime.fromtimestamp(sf.mtime, tz=timezone.utc)
                        img.status = "pending"
                        img.thumbnail_path = None  # regenerate

                        db.add(Job(type="thumbnail", image_id=img.id, priority=1))
                        db.add(Job(type="embed", image_id=img.id, priority=2))
                        img.embedding_status = "pending"  # reset
                        stats["modified"] += 1
                        stats["jobs"] += 2

        # 4. Find deleted files (in DB but not on disk)
        for path_str, img in existing_images.items():
            if path_str not in scanned_by_path and img.status != "deleted":
                img.status = "deleted"
                stats["deleted"] += 1

        # 5. Update folder last_scanned
        folder.last_scanned = datetime.now(timezone.utc)

    await db.commit()
    return stats
