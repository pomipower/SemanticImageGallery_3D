"""LanceDB vector store — embedded, serverless, handles >RAM datasets."""

import logging
from pathlib import Path

import numpy as np
import pyarrow as pa

from app.core.config import settings

logger = logging.getLogger(__name__)

_store = None  # module-level singleton

EMBEDDING_DIM = 512  # ViT-B-32


class VectorStore:
    """Thin wrapper around LanceDB for image embedding storage + ANN search."""

    def __init__(self, db_path: Path):
        import lancedb

        self.db = lancedb.connect(str(db_path))
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        existing = self.db.table_names()
        if "image_embeddings" not in existing:
            import lancedb

            schema = pa.schema(
                [
                    pa.field("image_id", pa.int64()),
                    pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
                    pa.field("file_path", pa.utf8()),
                ]
            )
            self.db.create_table("image_embeddings", schema=schema)
            logger.info("Created LanceDB table: image_embeddings")

    # ------------------------------------------------------------------
    def upsert_image_embedding(
        self, image_id: int, vector: np.ndarray, file_path: str
    ) -> None:
        table = self.db.open_table("image_embeddings")
        # Remove old entry if it exists
        try:
            table.delete(f"image_id = {image_id}")
        except Exception:
            pass
        table.add(
            [
                {
                    "image_id": int(image_id),
                    "vector": vector.tolist(),
                    "file_path": file_path,
                }
            ]
        )

    # ------------------------------------------------------------------
    def search_images(
        self, query_vector: np.ndarray, limit: int = 50
    ) -> list[dict]:
        """ANN search — returns [{image_id, file_path, _distance}, ...]."""
        table = self.db.open_table("image_embeddings")
        if table.count_rows() == 0:
            return []
        results = (
            table.search(query_vector.tolist())
            .metric("cosine")
            .limit(limit)
            .to_list()
        )
        return results

    # ------------------------------------------------------------------
    def delete_image(self, image_id: int) -> None:
        table = self.db.open_table("image_embeddings")
        try:
            table.delete(f"image_id = {image_id}")
        except Exception:
            pass

    def count(self) -> int:
        table = self.db.open_table("image_embeddings")
        return table.count_rows()


def get_vector_store() -> "VectorStore":
    """Return the module-level singleton."""
    global _store
    if _store is None:
        _store = VectorStore(settings.vectors_dir)
    return _store
