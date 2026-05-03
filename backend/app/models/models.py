"""SQLAlchemy ORM models — full schema (all milestones).

Only M1 tables (images, image_folders, jobs) are actively used initially.
Later milestone tables are included so the initial migration creates the
complete schema upfront.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# M1 — Core
# ---------------------------------------------------------------------------

class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    file_hash: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    format: Mapped[str | None] = mapped_column(String(10))
    exif_json: Mapped[str | None] = mapped_column(Text)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_msg: Mapped[str | None] = mapped_column(Text)

    # Relationships
    tags: Mapped[list["Tag"]] = relationship(back_populates="image", cascade="all, delete-orphan")
    captions: Mapped[list["Caption"]] = relationship(back_populates="image", cascade="all, delete-orphan")
    ocr_results: Mapped[list["OcrResult"]] = relationship(back_populates="image", cascade="all, delete-orphan")
    faces: Mapped[list["Face"]] = relationship(back_populates="image", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="image", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_images_file_hash", "file_hash"),
        Index("ix_images_status", "status"),
    )


class ImageFolder(Base):
    __tablename__ = "image_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    recursive: Mapped[bool] = mapped_column(Boolean, default=True)
    face_detection_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scanned: Mapped[datetime | None] = mapped_column(DateTime)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    image_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("images.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)
    retries: Mapped[int] = mapped_column(Integer, default=0)

    image: Mapped["Image | None"] = relationship(back_populates="jobs")

    __table_args__ = (
        Index("ix_jobs_status_priority", "status", "priority"),
    )


# ---------------------------------------------------------------------------
# M2 / M3 — Search + Metadata
# ---------------------------------------------------------------------------

class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_id: Mapped[int] = mapped_column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    tag: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20))  # clip | llm | user
    confidence: Mapped[float | None] = mapped_column(Float)

    image: Mapped["Image"] = relationship(back_populates="tags")


class Caption(Base):
    __tablename__ = "captions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_id: Mapped[int] = mapped_column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    image: Mapped["Image"] = relationship(back_populates="captions")


class OcrResult(Base):
    __tablename__ = "ocr_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_id: Mapped[int] = mapped_column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    image: Mapped["Image"] = relationship(back_populates="ocr_results")


# ---------------------------------------------------------------------------
# M4 — Face Pipeline
# ---------------------------------------------------------------------------

class Identity(Base):
    __tablename__ = "identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    thumbnail_face_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("faces.id", use_alter=True))

    faces: Mapped[list["Face"]] = relationship(back_populates="identity", foreign_keys="Face.identity_id")


class Face(Base):
    __tablename__ = "faces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    image_id: Mapped[int] = mapped_column(Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False)
    identity_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("identities.id"))
    bbox_x1: Mapped[int] = mapped_column(Integer)
    bbox_y1: Mapped[int] = mapped_column(Integer)
    bbox_x2: Mapped[int] = mapped_column(Integer)
    bbox_y2: Mapped[int] = mapped_column(Integer)
    crop_path: Mapped[str | None] = mapped_column(Text)
    det_score: Mapped[float | None] = mapped_column(Float)
    cluster_id: Mapped[int | None] = mapped_column(Integer)

    image: Mapped["Image"] = relationship(back_populates="faces")
    identity: Mapped["Identity | None"] = relationship(back_populates="faces", foreign_keys=[identity_id])


# ---------------------------------------------------------------------------
# M5 — Graph
# ---------------------------------------------------------------------------

class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    identity_a: Mapped[int] = mapped_column(Integer, ForeignKey("identities.id", ondelete="CASCADE"), nullable=False)
    identity_b: Mapped[int] = mapped_column(Integer, ForeignKey("identities.id", ondelete="CASCADE"), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("identity_a", "identity_b", name="uq_edge_pair"),
    )
