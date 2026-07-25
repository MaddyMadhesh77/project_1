from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory, MemoryVersion

# Reciprocal-rank-fusion constant. Standard default (Cormack et al.); flattens
# the influence of any single ranker so neither vector nor keyword search
# alone dominates the fused ordering.
_RRF_K = 60


@dataclass
class RetrievalHit:
    memory_id: uuid.UUID
    version_id: uuid.UUID
    text: str
    trust_score: float
    similarity: float  # cosine similarity (0-1) to the candidate, 0 if not in the vector result set
    rrf_score: float


async def hybrid_search(
    db: AsyncSession,
    *,
    embedding: list[float],
    text: str,
    top_k: int = 5,
) -> list[RetrievalHit]:
    """Hybrid retrieval over active memory versions (DESIGN.md 6.3).

    Merges pgvector cosine similarity with Postgres full-text rank via
    reciprocal-rank fusion. Only considers each memory's *current active*
    version -- retrieval reasons about the present state of the store, not
    superseded history.
    """
    vector_rows = (
        await db.execute(
            sa.select(
                MemoryVersion.version_id,
                MemoryVersion.memory_id,
                MemoryVersion.text,
                MemoryVersion.trust_score,
                (1 - MemoryVersion.embedding.cosine_distance(embedding)).label("similarity"),
            )
            .join(Memory, Memory.current_version_id == MemoryVersion.version_id)
            .where(MemoryVersion.is_active.is_(True))
            .order_by(MemoryVersion.embedding.cosine_distance(embedding))
            .limit(top_k)
        )
    ).all()

    keyword_rows: list = []
    if text.strip():
        keyword_rows = (
            await db.execute(
                sa.select(
                    MemoryVersion.version_id,
                    MemoryVersion.memory_id,
                    MemoryVersion.text,
                    MemoryVersion.trust_score,
                    sa.func.ts_rank(
                        sa.func.to_tsvector("english", MemoryVersion.text),
                        sa.func.plainto_tsquery("english", text),
                    ).label("rank"),
                )
                .join(Memory, Memory.current_version_id == MemoryVersion.version_id)
                .where(MemoryVersion.is_active.is_(True))
                .where(
                    sa.func.to_tsvector("english", MemoryVersion.text).op("@@")(
                        sa.func.plainto_tsquery("english", text)
                    )
                )
                .order_by(sa.desc("rank"))
                .limit(top_k)
            )
        ).all()

    fused: dict[uuid.UUID, dict] = {}

    for rank, row in enumerate(vector_rows):
        entry = fused.setdefault(
            row.version_id,
            {"memory_id": row.memory_id, "text": row.text, "trust_score": row.trust_score, "similarity": 0.0, "rrf": 0.0},
        )
        entry["similarity"] = float(row.similarity)
        entry["rrf"] += 1.0 / (_RRF_K + rank + 1)

    for rank, row in enumerate(keyword_rows):
        entry = fused.setdefault(
            row.version_id,
            {"memory_id": row.memory_id, "text": row.text, "trust_score": row.trust_score, "similarity": 0.0, "rrf": 0.0},
        )
        entry["rrf"] += 1.0 / (_RRF_K + rank + 1)

    hits = [
        RetrievalHit(
            memory_id=data["memory_id"],
            version_id=version_id,
            text=data["text"],
            trust_score=float(data["trust_score"]),
            similarity=data["similarity"],
            rrf_score=data["rrf"],
        )
        for version_id, data in fused.items()
    ]
    hits.sort(key=lambda h: h.rrf_score, reverse=True)
    return hits[:top_k]
