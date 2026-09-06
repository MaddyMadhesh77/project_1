from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services import analytics

router = APIRouter(tags=["analytics"])


class TrendPointOut(BaseModel):
    date: str
    store: int
    review: int
    reject: int
    rollbacks: int


class AnalyticsSummaryOut(BaseModel):
    status_counts: dict[str, int]
    decision_counts: dict[str, int]
    total_memories: int
    total_versions: int
    rollback_count: int
    trend: list[TrendPointOut]


@router.get("/analytics/summary", response_model=AnalyticsSummaryOut)
async def get_analytics_summary(db: AsyncSession = Depends(get_db)) -> AnalyticsSummaryOut:
    """DESIGN.md 8 Analytics.tsx data source -- counts by status/decision plus
    a daily trend of store/review/reject decisions and rollback events."""
    return AnalyticsSummaryOut(**await analytics.get_summary(db))
