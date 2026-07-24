from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Memory, MemoryVersion

router = APIRouter(tags=["memories"])


class MemoryOut(BaseModel):
    memory_id: uuid.UUID
    status: str
    current_version_id: uuid.UUID | None
    text: str | None
    trust_score: float | None
    decision: str | None
    version_count: int


class MemoryDetailOut(MemoryOut):
    trust_breakdown: dict | None
    content_hash: str | None


class MemoryVersionOut(BaseModel):
    version_id: uuid.UUID
    version_number: int
    text: str
    trust_score: float
    trust_breakdown: dict
    decision: str
    content_hash: str
    is_active: bool
    created_at: datetime


def _version_count_subquery():
    return (
        select(func.count(MemoryVersion.version_id))
        .where(MemoryVersion.memory_id == Memory.memory_id)
        .correlate(Memory)
        .scalar_subquery()
    )


@router.get("/memories", response_model=list[MemoryOut])
async def list_memories(status: str | None = None, db: AsyncSession = Depends(get_db)) -> list[MemoryOut]:
    stmt = (
        select(Memory, MemoryVersion, _version_count_subquery())
        .outerjoin(MemoryVersion, Memory.current_version_id == MemoryVersion.version_id)
        .order_by(Memory.created_at.desc())
    )
    if status:
        stmt = stmt.where(Memory.status == status)

    rows = (await db.execute(stmt)).all()
    return [
        MemoryOut(
            memory_id=memory.memory_id,
            status=memory.status,
            current_version_id=memory.current_version_id,
            text=version.text if version else None,
            trust_score=float(version.trust_score) if version else None,
            decision=version.decision if version else None,
            version_count=count,
        )
        for memory, version, count in rows
    ]


@router.get("/memories/{memory_id}", response_model=MemoryDetailOut)
async def get_memory(memory_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> MemoryDetailOut:
    memory = await db.get(Memory, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="memory not found")

    version = await db.get(MemoryVersion, memory.current_version_id) if memory.current_version_id else None
    count = (
        await db.execute(select(func.count(MemoryVersion.version_id)).where(MemoryVersion.memory_id == memory_id))
    ).scalar_one()

    return MemoryDetailOut(
        memory_id=memory.memory_id,
        status=memory.status,
        current_version_id=memory.current_version_id,
        text=version.text if version else None,
        trust_score=float(version.trust_score) if version else None,
        decision=version.decision if version else None,
        version_count=count,
        trust_breakdown=version.trust_breakdown if version else None,
        content_hash=version.content_hash if version else None,
    )


@router.get("/memories/{memory_id}/history", response_model=list[MemoryVersionOut])
async def get_memory_history(memory_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[MemoryVersionOut]:
    memory = await db.get(Memory, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="memory not found")

    versions = (
        await db.execute(
            select(MemoryVersion)
            .where(MemoryVersion.memory_id == memory_id)
            .order_by(MemoryVersion.version_number.asc())
        )
    ).scalars().all()

    return [
        MemoryVersionOut(
            version_id=v.version_id,
            version_number=v.version_number,
            text=v.text,
            trust_score=float(v.trust_score),
            trust_breakdown=v.trust_breakdown,
            decision=v.decision,
            content_hash=v.content_hash,
            is_active=v.is_active,
            created_at=v.created_at,
        )
        for v in versions
    ]
