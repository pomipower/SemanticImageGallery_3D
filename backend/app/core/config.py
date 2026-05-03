"""Application configuration — single source of truth for all settings."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All app settings. Override via environment variables prefixed with SIG_."""

    # --- App ---
    app_name: str = "SemanticImageGallery"
    debug: bool = False

    # --- Data directory (user-level, outside project) ---
    data_dir: Path = Path.home() / ".semantic-gallery" / "data"

    # --- Database ---
    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.data_dir / 'main.db'}"

    @property
    def sync_database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'main.db'}"

    # --- Derived paths ---
    @property
    def thumbs_dir(self) -> Path:
        return self.data_dir / "thumbs"

    @property
    def faces_dir(self) -> Path:
        return self.data_dir / "faces"

    @property
    def vectors_dir(self) -> Path:
        return self.data_dir / "vectors"

    # --- Thumbnail ---
    thumbnail_max_size: int = 300
    thumbnail_quality: int = 85

    # --- Worker ---
    worker_poll_interval: float = 0.5
    max_retries: int = 3

    # --- File scanning ---
    supported_extensions: frozenset[str] = frozenset({".jpg", ".jpeg", ".png"})

    model_config = {"env_prefix": "SIG_"}

    # --- Helpers ---
    def ensure_dirs(self) -> None:
        """Create all required data directories."""
        for d in (self.data_dir, self.thumbs_dir, self.faces_dir, self.vectors_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
