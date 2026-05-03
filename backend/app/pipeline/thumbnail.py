"""Thumbnail generation + EXIF extraction (Pillow-based)."""

import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image as PILImage
from PIL import ExifTags

from app.core.config import settings


def generate_thumbnail(image_path: Path, file_hash: str) -> Path:
    """
    Resize to fit within thumbnail_max_size, save as JPEG.

    Returns the absolute path to the thumbnail file.
    Storage layout: {thumbs_dir}/{hash[:2]}/{hash}.jpg
    """
    sub_dir = settings.thumbs_dir / file_hash[:2]
    sub_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = sub_dir / f"{file_hash}.jpg"

    if thumb_path.exists():
        return thumb_path

    with PILImage.open(image_path) as img:
        img.thumbnail(
            (settings.thumbnail_max_size, settings.thumbnail_max_size),
            PILImage.Resampling.LANCZOS,
        )
        # Convert to RGB for JPEG (handles RGBA PNGs)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.save(thumb_path, "JPEG", quality=settings.thumbnail_quality)

    return thumb_path


def get_image_dimensions(image_path: Path) -> tuple[int, int]:
    """Return (width, height) without loading full image into memory."""
    with PILImage.open(image_path) as img:
        return img.size


def extract_exif(image_path: Path) -> str | None:
    """
    Extract EXIF data as a JSON string.

    Returns None if no EXIF data found or file is not JPEG.
    """
    try:
        with PILImage.open(image_path) as img:
            raw_exif = img._getexif()
            if not raw_exif:
                return None

            decoded: dict[str, str] = {}
            for tag_id, value in raw_exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                # Convert bytes and other non-serializable types
                if isinstance(value, bytes):
                    continue  # skip binary blobs (MakerNote, etc.)
                if isinstance(value, (int, float, str)):
                    decoded[tag_name] = str(value)
                elif isinstance(value, tuple):
                    decoded[tag_name] = str(value)
                # Skip IFDRational and other complex types

            return json.dumps(decoded, ensure_ascii=False) if decoded else None
    except Exception:
        return None


def get_image_format(image_path: Path) -> str:
    """Return normalized format string (jpg, png)."""
    ext = image_path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return "jpg"
    return ext.lstrip(".")
