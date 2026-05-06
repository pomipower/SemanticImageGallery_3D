"""Search API endpoint — hybrid vector + keyword search."""

import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import Image
from app.search.engine import hybrid_search
from app.schemas.schemas import ImageRead

router = APIRouter(prefix="/search", tags=["search"])
logger = logging.getLogger(__name__)


@router.get("")
async def search_images(
    q: str = Query(..., min_length=1, description="Natural language query"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    Hybrid search: encodes query with CLIP, searches LanceDB + FTS5,
    fuses results with Reciprocal Rank Fusion.
    """
    search_result = await hybrid_search(db, query=q, limit=limit, offset=offset)

    # Hydrate with full image data
    image_ids = [r["image_id"] for r in search_result["results"]]
    if not image_ids:
        return {"results": [], "total": 0, "query": q}

    result = await db.execute(
        select(Image).where(Image.id.in_(image_ids))
    )
    images_by_id = {img.id: img for img in result.scalars().all()}

    hydrated = []
    for r in search_result["results"]:
        img = images_by_id.get(r["image_id"])
        if img:
            hydrated.append({
                "image": ImageRead.model_validate(img).model_dump(),
                "score": r["score"],
                "vector_distance": r["vector_distance"],
                "source": r["source"],
            })

    return {
        "results": hydrated,
        "total": search_result["total"],
        "query": q,
    }
