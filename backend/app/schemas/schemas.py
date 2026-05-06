"""Pydantic schemas for API request/response serialization."""

from datetime import datetime
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Image Folder
# ---------------------------------------------------------------------------

class FolderCreate(BaseModel):
    path: str
    recursive: bool = True
    face_detection_enabled: bool = True


class FolderRead(BaseModel):
    id: int
    path: str
    recursive: bool
    face_detection_enabled: bool
    last_scanned: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

class ImageRead(BaseModel):
    id: int
    file_path: str
    file_hash: str
    file_size: int | None = None
    width: int | None = None
    height: int | None = None
    format: str | None = None
    exif_json: str | None = None
    thumbnail_path: str | None = None
    indexed_at: datetime | None = None
    modified_at: datetime | None = None
    status: str
    embedding_status: str = "pending"

    model_config = {"from_attributes": True}


class ImageList(BaseModel):
    items: list[ImageRead]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class JobRead(BaseModel):
    id: int
    type: str
    image_id: int | None = None
    status: str
    priority: int
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    retries: int

    model_config = {"from_attributes": True}


class JobList(BaseModel):
    items: list[JobRead]
    total: int


# ---------------------------------------------------------------------------
# Scan request / response
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    folder_id: int | None = None  # None → scan all registered folders


class ScanResponse(BaseModel):
    new_images: int
    modified_images: int
    deleted_images: int
    jobs_created: int


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class StatsRead(BaseModel):
    total_images: int
    indexed_images: int
    pending_images: int
    error_images: int
    total_folders: int
    queued_jobs: int
    running_jobs: int
