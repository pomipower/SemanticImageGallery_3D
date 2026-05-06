"""Hybrid search engine — vector (LanceDB ANN) + keyword (FTS5) with RRF fusion."""

import logging
from collections import defaultdict

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.clip import get_clip_encoder
from app.core.vector_store import get_vector_store

logger = logging.getLogger(__name__)

RRF_K = 60  # standard Reciprocal Rank Fusion constant


async def hybrid_search(
    db: AsyncSession,
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """
    Execute hybrid search: vector + keyword, fused with RRF.

    Returns {results: [...], total: int}.
    Each result has: image_id, score, source (vector|keyword|both).
    """
    encoder = get_clip_encoder()
    store = get_vector_store()

    # ── 1. Vector search (semantic) ──────────────────────────────────
    query_vector = encoder.encode_text(query)
    vector_hits = store.search_images(query_vector, limit=50)
    vector_ranking: list[int] = [int(h["image_id"]) for h in vector_hits]
    vector_scores = {int(h["image_id"]): float(h.get("_distance", 0)) for h in vector_hits}

    # ── 2. FTS5 keyword search ───────────────────────────────────────
    fts_ranking = await _fts5_search(db, query, limit=50)

    # ── 3. RRF fusion ────────────────────────────────────────────────
    fused = _reciprocal_rank_fusion([vector_ranking, fts_ranking])

    # Track which systems contributed
    vector_set = set(vector_ranking)
    fts_set = set(fts_ranking)

    results = []
    for image_id, rrf_score in fused:
        source = "both" if image_id in vector_set and image_id in fts_set else (
            "vector" if image_id in vector_set else "keyword"
        )
        results.append({
            "image_id": image_id,
            "score": round(rrf_score, 6),
            "vector_distance": round(vector_scores.get(image_id, 1.0), 4),
            "source": source,
        })

    total = len(results)
    page_results = results[offset : offset + limit]

    return {"results": page_results, "total": total}


async def vector_only_search(
    query: str,
    limit: int = 20,
) -> list[dict]:
    """Pure vector search — useful for debugging / comparison."""
    encoder = get_clip_encoder()
    store = get_vector_store()
    query_vector = encoder.encode_text(query)
    hits = store.search_images(query_vector, limit=limit)
    return [
        {"image_id": int(h["image_id"]), "distance": float(h.get("_distance", 0))}
        for h in hits
    ]


# ── FTS5 helpers ─────────────────────────────────────────────────────

async def _fts5_search(db: AsyncSession, query: str, limit: int = 50) -> list[int]:
    """
    Search FTS5 virtual table, return ranked image_id list.

    Falls back to empty list if FTS5 table doesn't exist or query is empty.
    """
    if not query.strip():
        return []

    # Sanitize for FTS5: escape double quotes, wrap tokens in quotes
    safe_query = query.replace('"', '""')
    # Use simple prefix matching for partial words
    tokens = safe_query.split()
    fts_query = " OR ".join(f'"{t}"*' for t in tokens if t)

    try:
        result = await db.execute(
            text(
                "SELECT rowid, rank FROM images_fts "
                "WHERE images_fts MATCH :q "
                "ORDER BY rank LIMIT :lim"
            ),
            {"q": fts_query, "lim": limit},
        )
        rows = result.fetchall()
        return [int(row[0]) for row in rows]
    except Exception as e:
        logger.debug("FTS5 search failed (table may not exist yet): %s", e)
        return []


# ── RRF ──────────────────────────────────────────────────────────────

def _reciprocal_rank_fusion(
    rankings: list[list[int]], k: int = RRF_K
) -> list[tuple[int, float]]:
    """
    Reciprocal Rank Fusion — merge multiple ranked lists.

    score(d) = Σ  1 / (k + rank_i)   for each ranking that contains d
    """
    scores: dict[int, float] = defaultdict(float)

    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] += 1.0 / (k + rank + 1)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
