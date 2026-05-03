"""File discovery — walks registered folders and returns image file metadata."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings


@dataclass(frozen=True)
class ScannedFile:
    """Lightweight DTO for a discovered image file."""
    path: Path
    size: int
    mtime: float  # os.stat st_mtime


def compute_file_hash(file_path: Path, chunk_size: int = 65536) -> str:
    """SHA-256 of file contents, read in 64 KB chunks."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha.update(chunk)
    return sha.hexdigest()


def scan_folder(folder_path: str | Path, recursive: bool = True) -> list[ScannedFile]:
    """
    Walk *folder_path* and return every supported image file.

    Uses os.scandir for performance (avoids stat calls where possible).
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")

    results: list[ScannedFile] = []
    exts = settings.supported_extensions

    def _scan(directory: Path) -> None:
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    if entry.is_file(follow_symlinks=False):
                        ext = Path(entry.name).suffix.lower()
                        if ext in exts:
                            stat = entry.stat(follow_symlinks=False)
                            results.append(
                                ScannedFile(
                                    path=Path(entry.path),
                                    size=stat.st_size,
                                    mtime=stat.st_mtime,
                                )
                            )
                    elif recursive and entry.is_dir(follow_symlinks=False):
                        _scan(Path(entry.path))
        except PermissionError:
            pass  # skip inaccessible directories silently

    _scan(folder)
    return results
