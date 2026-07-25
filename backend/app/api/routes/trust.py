from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import MemoryVersion

router = APIRouter(tags=["trust"])


class TrustOut(BaseModel):
    version_id: uuid.UUID
    trust_score: float
    trust_breakdown: dict
    decision: str


@router.get("/trust/{version_id}", response_model=TrustOut)
async def get_trust(version_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> TrustOut:
    version = await db.get(MemoryVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")

    return TrustOut(
        version_id=version.version_id,
        trust_score=float(version.trust_score),
        trust_breakdown=version.trust_breakdown,
        decision=version.decision,
    )
