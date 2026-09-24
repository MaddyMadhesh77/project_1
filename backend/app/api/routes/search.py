from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services import retrieval
from app.services.embedding import get_embedding_service

router = APIRouter(tags=["search"])


class SearchHitOut(BaseModel):
    memory_id: uuid.UUID
    version_id: uuid.UUID
    text: str
    trust_score: float
    similarity: float


@router.get("/search", response_model=list[SearchHitOut])
async def search_memories(
    q: str = Query(min_length=1, max_length=4000),
    top_k: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
) -> list[SearchHitOut]:
    """Exposes the same hybrid retrieval (services/retrieval.py) the chat
    pipeline uses internally for its own trust-scoring, per DESIGN.md §9 flow
    5 -- a direct demo of the retrieval mechanism rather than a new one."""
    # A blank query used to be embedded as-is and return arbitrary
    # nearest neighbours (the keyword leg skips blank text entirely).
    if not q.strip():
        raise HTTPException(status_code=422, detail="q must not be blank")
    embedding_service = get_embedding_service()
    embedding = await embedding_service.aembed(q)

    hits = await retrieval.hybrid_search(db, embedding=embedding, text=q, top_k=top_k)

    return [
        SearchHitOut(
            memory_id=hit.memory_id,
            version_id=hit.version_id,
            text=hit.text,
            trust_score=hit.trust_score,
            similarity=hit.similarity,
        )
        for hit in hits
    ]
