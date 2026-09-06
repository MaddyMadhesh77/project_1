from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Memory, MemoryVersion, TrustEvent

router = APIRouter(tags=["logs"])


class LogEntryOut(BaseModel):
    event_id: uuid.UUID
    memory_id: uuid.UUID
    version_id: uuid.UUID
    text: str
    event_type: str
    decision: str
    trust_score: float | None
    created_at: datetime


class LogsPageOut(BaseModel):
    items: list[LogEntryOut]
    total: int


@router.get("/logs", response_model=LogsPageOut)
async def get_logs(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)) -> LogsPageOut:
    """DESIGN.md 8 Logs.tsx data source -- raw trust_events feed, newest
    first, joined with the version/memory it scored so each row is
    self-describing without a follow-up request."""
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    total = (await db.execute(select(func.count()).select_from(TrustEvent))).scalar_one()

    rows = (
        await db.execute(
            select(TrustEvent, MemoryVersion, Memory)
            .join(MemoryVersion, MemoryVersion.version_id == TrustEvent.version_id)
            .join(Memory, Memory.memory_id == MemoryVersion.memory_id)
            .order_by(TrustEvent.created_at.desc(), TrustEvent.event_id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    items = [
        LogEntryOut(
            event_id=event.event_id,
            memory_id=memory.memory_id,
            version_id=version.version_id,
            text=version.text,
            event_type=event.event_type,
            decision=version.decision,
            trust_score=float(event.trust_score) if event.trust_score is not None else None,
            created_at=event.created_at,
        )
        for event, version, memory in rows
    ]

    return LogsPageOut(items=items, total=total)
